"""学习任务业务逻辑（功能 6）。

「完成任务」是一个**原子操作**：同一事务里改任务状态 + 写学习记录，
避免出现「任务完成了但时长没记上」这种统计缺口。
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequest, NotFound, PlanTasksExist
from app.models import Material, StudyPlan, StudyRecord, StudyTask, utcnow
from app.schemas.task import TaskCompleteIn, TaskCreate, TaskUpdate


async def _ensure_refs(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    plan_id: uuid.UUID | None,
    material_id: uuid.UUID | None,
) -> None:
    if plan_id is not None:
        owned = await db.scalar(
            select(StudyPlan.id).where(
                StudyPlan.id == plan_id,
                StudyPlan.user_id == user_id,
                StudyPlan.deleted_at.is_(None),
            )
        )
        if owned is None:
            raise NotFound("计划不存在")
    if material_id is not None:
        owned = await db.scalar(
            select(Material.id).where(
                Material.id == material_id,
                Material.user_id == user_id,
                Material.deleted_at.is_(None),
            )
        )
        if owned is None:
            raise NotFound("资料不存在")


async def get_owned(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> StudyTask:
    result = await db.execute(
        select(StudyTask).where(
            StudyTask.id == task_id,
            StudyTask.user_id == user_id,
            StudyTask.deleted_at.is_(None),
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFound("任务不存在")
    return task


async def list_tasks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    offset: int,
    limit: int,
    plan_id: uuid.UUID | None = None,
    plan_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
) -> tuple[list[StudyTask], int]:
    conditions = [StudyTask.user_id == user_id, StudyTask.deleted_at.is_(None)]
    if plan_id:
        conditions.append(StudyTask.plan_id == plan_id)
    if plan_date:
        conditions.append(StudyTask.plan_date == plan_date)
    if date_from:
        conditions.append(StudyTask.plan_date >= date_from)
    if date_to:
        conditions.append(StudyTask.plan_date <= date_to)
    if status:
        conditions.append(StudyTask.status == status)

    total = await db.scalar(select(func.count()).select_from(StudyTask).where(*conditions))
    result = await db.execute(
        select(StudyTask)
        .where(*conditions)
        .order_by(StudyTask.plan_date.desc(), StudyTask.order_no.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), int(total or 0)


async def create_task(db: AsyncSession, *, user_id: uuid.UUID, data: TaskCreate) -> StudyTask:
    await _ensure_refs(db, user_id, plan_id=data.plan_id, material_id=data.material_id)

    task = StudyTask(user_id=user_id, **data.model_dump())
    db.add(task)
    try:
        await db.commit()
    except IntegrityError as exc:
        # 同一计划同一天只能有一条任务（部分唯一索引）
        await db.rollback()
        raise PlanTasksExist from exc

    await db.refresh(task)
    return task


async def update_task(db: AsyncSession, task: StudyTask, data: TaskUpdate) -> StudyTask:
    changes = data.model_dump(exclude_unset=True)
    if changes.get("material_id") is not None:
        await _ensure_refs(db, task.user_id, plan_id=None, material_id=changes["material_id"])

    if "status" in changes and changes["status"] == "done" and task.completed_at is None:
        task.completed_at = utcnow()
    if "status" in changes and changes["status"] in ("pending", "doing", "skipped"):
        task.completed_at = None

    for field, value in changes.items():
        setattr(task, field, value)

    task.updated_at = utcnow()
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise PlanTasksExist("该计划在这一天已有任务") from exc

    await db.refresh(task)
    return task


async def complete_task(
    db: AsyncSession, task: StudyTask, data: TaskCompleteIn
) -> tuple[StudyTask, StudyRecord | None]:
    if task.status == "done":
        raise BadRequest("该任务已完成")

    moment = utcnow()
    task.status = "done"
    task.completed_at = moment
    task.updated_at = moment

    record: StudyRecord | None = None
    if data.create_record:
        record = StudyRecord(
            user_id=task.user_id,
            task_id=task.id,
            material_id=task.material_id,
            # 任务完成自动生成的学习记录没有更细的类型信息，统一记为 other
            type="other",
            started_at=moment,
            duration_minutes=data.duration_minutes,
            content=(data.content or task.title)[:500],
        )
        db.add(record)

    # 一次 commit 同时落任务状态与学习记录
    await db.commit()
    await db.refresh(task)
    if record is not None:
        await db.refresh(record)
    return task, record


async def delete_task(db: AsyncSession, task: StudyTask) -> None:
    task.deleted_at = utcnow()
    task.updated_at = utcnow()
    await db.commit()
