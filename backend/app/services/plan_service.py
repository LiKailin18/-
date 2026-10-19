"""学习计划业务逻辑（功能 5）。

「生成每日任务」是本模块最关键的部分：
- 幂等：靠 study_task 的部分唯一索引 (plan_id, plan_date) WHERE deleted_at IS NULL
- 全部已存在 → 409 PLAN_001（避免用户重复点击还以为成功）
"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequest, NotFound, PlanTasksExist
from app.models import Material, StudyPlan, StudyTask, utcnow
from app.schemas.plan import GenerateTasksOut, PlanCreate, PlanProgress, PlanUpdate
from app.utils.time import date_range


async def ensure_materials_owned(
    db: AsyncSession, user_id: uuid.UUID, material_ids: list[uuid.UUID]
) -> None:
    """计划里引用的资料必须都属于本人且未删除，否则统一 404。"""
    if not material_ids:
        return
    wanted = set(material_ids)
    found = set(
        await db.scalars(
            select(Material.id).where(
                Material.id.in_(wanted),
                Material.user_id == user_id,
                Material.deleted_at.is_(None),
            )
        )
    )
    if wanted - found:
        raise NotFound("引用的资料不存在")


async def create_plan(db: AsyncSession, *, user_id: uuid.UUID, data: PlanCreate) -> StudyPlan:
    await ensure_materials_owned(db, user_id, data.material_ids)

    plan = StudyPlan(user_id=user_id, **data.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def list_plans(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    offset: int,
    limit: int,
    status: str | None = None,
) -> tuple[list[StudyPlan], int, dict[uuid.UUID, PlanProgress]]:
    conditions = [StudyPlan.user_id == user_id, StudyPlan.deleted_at.is_(None)]
    if status:
        conditions.append(StudyPlan.status == status)

    total = await db.scalar(select(func.count()).select_from(StudyPlan).where(*conditions))
    result = await db.execute(
        select(StudyPlan)
        .where(*conditions)
        .order_by(StudyPlan.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    plans = list(result.scalars().all())

    return plans, int(total or 0), await progress_map(db, [plan.id for plan in plans])


async def progress_map(
    db: AsyncSession, plan_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PlanProgress]:
    """一次分组查询拿到这一页计划的进度（避免 N+1）。

    统计口径：`skipped` 不计入总数（与 /stats 保持一致）。
    """
    if not plan_ids:
        return {}

    rows = await db.execute(
        select(
            StudyTask.plan_id,
            func.count().label("total"),
            func.count().filter(StudyTask.status == "done").label("done"),
        )
        .where(
            StudyTask.plan_id.in_(plan_ids),
            StudyTask.deleted_at.is_(None),
            StudyTask.status != "skipped",
        )
        .group_by(StudyTask.plan_id)
    )

    progress: dict[uuid.UUID, PlanProgress] = {}
    for plan_id, total, done in rows:
        if plan_id is None:
            continue
        progress[plan_id] = PlanProgress(
            task_total=int(total),
            task_done=int(done),
            progress=round(done / total, 4) if total else 0.0,
        )
    return progress


async def progress_for(db: AsyncSession, plan_id: uuid.UUID) -> PlanProgress:
    return (await progress_map(db, [plan_id])).get(plan_id, PlanProgress())


async def get_owned(db: AsyncSession, user_id: uuid.UUID, plan_id: uuid.UUID) -> StudyPlan:
    result = await db.execute(
        select(StudyPlan).where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == user_id,
            StudyPlan.deleted_at.is_(None),
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise NotFound("计划不存在")
    return plan


async def update_plan(db: AsyncSession, plan: StudyPlan, data: PlanUpdate) -> StudyPlan:
    # 契约 §7：日期不可改（已生成的任务会与区间不一致）
    if data.start_date is not None or data.end_date is not None:
        raise BadRequest("计划的开始/结束日期不可修改，请新建计划")

    changes = data.model_dump(exclude_unset=True, exclude={"start_date", "end_date"})
    if changes.get("material_ids") is not None:
        await ensure_materials_owned(db, plan.user_id, changes["material_ids"])

    for field, value in changes.items():
        setattr(plan, field, value)

    plan.updated_at = utcnow()
    await db.commit()
    await db.refresh(plan)
    return plan


async def delete_plan(db: AsyncSession, plan: StudyPlan) -> None:
    """软删计划，并级联软删**未完成**的任务（已完成的保留用于统计）。"""
    moment = utcnow()
    await db.execute(
        update(StudyTask)
        .where(
            StudyTask.plan_id == plan.id,
            StudyTask.deleted_at.is_(None),
            StudyTask.status != "done",
        )
        .values(deleted_at=moment, updated_at=moment)
    )
    plan.deleted_at = moment
    plan.updated_at = moment
    await db.commit()


async def generate_tasks(
    db: AsyncSession, plan: StudyPlan, *, overwrite: bool = False
) -> GenerateTasksOut:
    days = date_range(plan.start_date, plan.end_date)

    if overwrite:
        # 只重建 pending 的（done / skipped 保留，避免抹掉历史）
        moment = utcnow()
        await db.execute(
            update(StudyTask)
            .where(
                StudyTask.plan_id == plan.id,
                StudyTask.deleted_at.is_(None),
                StudyTask.status == "pending",
            )
            .values(deleted_at=moment, updated_at=moment)
        )
        await db.commit()

    existing = set(
        await db.scalars(
            select(StudyTask.plan_date).where(
                StudyTask.plan_id == plan.id, StudyTask.deleted_at.is_(None)
            )
        )
    )
    missing = [day for day in days if day not in existing]
    if not missing:
        raise PlanTasksExist

    tasks = [
        StudyTask(
            user_id=plan.user_id,
            plan_id=plan.id,
            plan_date=day,
            title=f"{plan.title} · 第 {days.index(day) + 1} 天",
            est_minutes=plan.daily_minutes,
            order_no=days.index(day) + 1,
            status="pending",
        )
        for day in missing
    ]
    db.add_all(tasks)
    await db.commit()

    return GenerateTasksOut(
        plan_id=plan.id,
        created=len(tasks),
        skipped=len(days) - len(tasks),
        dates=missing,
    )
