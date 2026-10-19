"""学习计划表模型（docs/db.md §3.4）。"""

import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, CheckConstraint, Date, DateTime, Index, SmallInteger, Uuid, text
from sqlmodel import Field, SQLModel

from app.models.user import utcnow

PLAN_STATUSES = ("draft", "active", "done", "archived")


class StudyPlan(SQLModel, table=True):
    __tablename__ = "study_plan"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'done', 'archived')", name="ck_plan_status"
        ),
        CheckConstraint("daily_minutes BETWEEN 1 AND 600", name="ck_plan_daily_minutes"),
        CheckConstraint("end_date >= start_date", name="ck_plan_date_order"),
        Index(
            "ix_plan_user_status",
            "user_id",
            "status",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_plan_material_ids", "material_ids", postgresql_using="gin"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)

    title: str = Field(max_length=200)
    subject: str | None = Field(default=None, max_length=64)
    goal: str | None = Field(default=None, max_length=500)

    start_date: date = Field(sa_type=Date)
    end_date: date = Field(sa_type=Date)
    daily_minutes: int = Field(default=60, sa_type=SmallInteger)

    status: str = Field(default="active", max_length=16)

    # 关联资料：只用于展示与过滤，不建外键（docs/db.md §3.4）
    material_ids: list[uuid.UUID] = Field(default_factory=list, sa_type=ARRAY(Uuid))

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
