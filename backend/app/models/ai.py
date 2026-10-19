"""AI 生成物归档与调用流水（docs/db.md §3.11、§3.12）。

- `ai_generation`：总结与建议的归档（可对比多次生成）
- `ai_usage`：一次请求写一行，token 为**多轮累加值**；配额按它当日计数
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.user import utcnow

GENERATION_SCENES = ("summary", "advice")
USAGE_SCENES = ("qa", "summary", "quiz", "advice")


class AiGeneration(SQLModel, table=True):
    __tablename__ = "ai_generation"
    __table_args__ = (
        CheckConstraint("scene IN ('summary', 'advice')", name="ck_aigen_scene"),
        CheckConstraint("ref_type IN ('material', 'user')", name="ck_aigen_ref_type"),
        Index("ix_aigen_user_scene_created", "user_id", "scene", "created_at"),
        Index("ix_aigen_ref", "ref_type", "ref_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)

    scene: str = Field(max_length=16)
    # 多态归档：summary 指向 material，advice 指向 user（不建外键）
    ref_type: str = Field(max_length=16)
    ref_id: uuid.UUID | None = Field(default=None)

    input_params: dict = Field(default_factory=dict, sa_type=JSONB)
    output_md: str | None = Field(default=None, sa_type=Text)
    output_data: dict | None = Field(default=None, sa_type=JSONB)

    model: str = Field(max_length=64)
    prompt_tokens: int = Field(default=0, sa_type=Integer)
    completion_tokens: int = Field(default=0, sa_type=Integer)
    latency_ms: int | None = Field(default=None, sa_type=Integer)

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class AiUsage(SQLModel, table=True):
    __tablename__ = "ai_usage"
    __table_args__ = (
        CheckConstraint(
            "scene IN ('qa', 'summary', 'quiz', 'advice')", name="ck_usage_scene"
        ),
        Index("ix_usage_user_created", "user_id", "created_at"),
        Index("ix_usage_scene_created", "scene", "created_at"),
        # 管理端全站统计按纯时间范围扫描
        Index("ix_usage_created", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)

    scene: str = Field(max_length=16)
    model: str = Field(max_length=64)

    prompt_tokens: int = Field(default=0, sa_type=Integer)
    completion_tokens: int = Field(default=0, sa_type=Integer)
    total_tokens: int = Field(default=0, sa_type=Integer)
    # agent 实际步数（工具调用轮次 + 1），用于观察成本是否异常
    steps: int = Field(default=1, sa_type=SmallInteger)

    latency_ms: int | None = Field(default=None, sa_type=Integer)
    ok: bool = Field(default=True, sa_type=Boolean)
    error_code: str | None = Field(default=None, max_length=16)

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
