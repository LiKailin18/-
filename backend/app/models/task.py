"""每日学习任务表模型（docs/db.md §3.5）。

关键约束：**部分唯一索引** (plan_id, plan_date) WHERE plan_id IS NOT NULL AND deleted_at IS NULL。
它是「生成任务幂等」的地基 —— 普通 UNIQUE 会把软删除的行也算进去，
删了任务后就无法重建同一天的任务（CLAUDE.md §6）。
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, SmallInteger, Text, text
from sqlmodel import Field, SQLModel

from app.models.user import utcnow

TASK_STATUSES = ("pending", "doing", "done", "skipped")


class StudyTask(SQLModel, table=True):
    __tablename__ = "study_task"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'doing', 'done', 'skipped')", name="ck_task_status"
        ),
        CheckConstraint("est_minutes BETWEEN 1 AND 600", name="ck_task_est_minutes"),
        Index(
            "uq_task_plan_date",
            "plan_id",
            "plan_date",
            unique=True,
            postgresql_where=text("plan_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index(
            "ix_task_user_date",
            "user_id",
            "plan_date",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_task_user_status",
            "user_id",
            "status",
            "plan_date",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # user_id 冗余自 plan，便于直接按用户查询（避免每次都 join）
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)
    plan_id: uuid.UUID | None = Field(
        default=None, foreign_key="study_plan.id", ondelete="CASCADE", index=True
    )
    material_id: uuid.UUID | None = Field(
        default=None, foreign_key="material.id", ondelete="SET NULL", index=True
    )

    plan_date: date = Field(sa_type=Date)
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, sa_type=Text)
    order_no: int = Field(default=1, sa_type=SmallInteger)
    est_minutes: int = Field(default=30, sa_type=SmallInteger)
    status: str = Field(default="pending", max_length=16)
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
