"""学习记录业务逻辑（功能 12）。

学习记录是统计与推荐的数据源：按 `started_at` 分日聚合（M6 会直接用它）。
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.models import Material, StudyRecord, StudyTask, utcnow
from app.schemas.record import RecordCreate, RecordUpdate
from app.utils.time import app_tz


async def _ensure_refs(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    task_id: uuid.UUID | None,
    material_id: uuid.UUID | None,
) -> None:
    if task_id is not None:
        owned = await db.scalar(
            select(StudyTask.id).where(
                StudyTask.id == task_id,
                StudyTask.user_id == user_id,
                StudyTask.deleted_at.is_(None),
            )
        )
        if owned is None:
            raise NotFound("任务不存在")
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


async def create_record(
    db: AsyncSession, *, user_id: uuid.UUID, data: RecordCreate
) -> StudyRecord:
    await _ensure_refs(db, user_id, task_id=data.task_id, material_id=data.material_id)

    record = StudyRecord(user_id=user_id, **data.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def list_records(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    offset: int,
    limit: int,
    date_from: date | None = None,
    date_to: date | None = None,
    record_type: str | None = None,
    plan_id: uuid.UUID | None = None,
) -> tuple[list[StudyRecord], int]:
    conditions = [StudyRecord.user_id == user_id, StudyRecord.deleted_at.is_(None)]

    # 按日期过滤要按业务时区切日，而不是 UTC
    tz = app_tz()
    if date_from:
        conditions.append(
            StudyRecord.started_at >= datetime.combine(date_from, datetime.min.time(), tz)
        )
    if date_to:
        # 包含结束当天：< 次日 00:00
        conditions.append(
            StudyRecord.started_at
            < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tz)
        )
    if record_type:
        conditions.append(StudyRecord.type == record_type)

    stmt = select(StudyRecord)
    count_stmt = select(func.count()).select_from(StudyRecord)

    if plan_id is not None:
        # 按计划过滤需要经任务关联
        stmt = stmt.join(StudyTask, StudyTask.id == StudyRecord.task_id)
        count_stmt = count_stmt.join(StudyTask, StudyTask.id == StudyRecord.task_id)
        conditions.append(StudyTask.plan_id == plan_id)

    total = await db.scalar(count_stmt.where(*conditions))
    result = await db.execute(
        stmt.where(*conditions).order_by(StudyRecord.started_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_owned(db: AsyncSession, user_id: uuid.UUID, record_id: uuid.UUID) -> StudyRecord:
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.id == record_id,
            StudyRecord.user_id == user_id,
            StudyRecord.deleted_at.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise NotFound("学习记录不存在")
    return record


async def update_record(
    db: AsyncSession, record: StudyRecord, data: RecordUpdate
) -> StudyRecord:
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(record, field, value)
    record.updated_at = utcnow()
    await db.commit()
    await db.refresh(record)
    return record


async def delete_record(db: AsyncSession, record: StudyRecord) -> None:
    record.deleted_at = utcnow()
    record.updated_at = utcnow()
    await db.commit()
