"""学习记录表模型（docs/db.md §3.6）。

study_record 是统计与推荐的数据源：`started_at` 是统计的基准时间（按它分日聚合）。
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, text
from sqlmodel import Field, SQLModel

from app.models.user import utcnow

RECORD_TYPES = ("reading", "video", "practice", "review", "other")


class StudyRecord(SQLModel, table=True):
    __tablename__ = "study_record"
    __table_args__ = (
        CheckConstraint(
            "type IN ('reading', 'video', 'practice', 'review', 'other')", name="ck_record_type"
        ),
        CheckConstraint("duration_minutes BETWEEN 1 AND 1440", name="ck_record_duration"),
        Index(
            "ix_record_user_started",
            "user_id",
            "started_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # 管理端全站趋势要按纯时间范围扫描，复合索引服务不了
        Index(
            "ix_record_started",
            "started_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_record_task", "task_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)
    task_id: uuid.UUID | None = Field(
        default=None, foreign_key="study_task.id", ondelete="SET NULL"
    )
    material_id: uuid.UUID | None = Field(
        default=None, foreign_key="material.id", ondelete="SET NULL"
    )

    type: str = Field(default="reading", max_length=16)
    started_at: datetime = Field(sa_type=DateTime(timezone=True))
    duration_minutes: int = Field(sa_type=SmallInteger)
    content: str | None = Field(default=None, max_length=500)

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
