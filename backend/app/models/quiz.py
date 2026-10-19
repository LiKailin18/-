"""测试题与答卷表模型（docs/db.md §3.9、§3.10）。

题目结构存在 `question_data` JSONB 里（见 docs/db.md §4.1），
不拆成「题目表 + 选项表」—— 因为题目只在 AI 生成时整体产生、整体展示。
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from app.models.user import utcnow


class Quiz(SQLModel, table=True):
    __tablename__ = "quiz"
    __table_args__ = (
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_quiz_difficulty"),
        Index("ix_quiz_user_created", "user_id", "created_at"),
        Index("ix_quiz_material", "material_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)
    material_id: uuid.UUID | None = Field(
        default=None, foreign_key="material.id", ondelete="SET NULL"
    )

    title: str = Field(max_length=200)
    question_count: int = Field(sa_type=SmallInteger)
    types: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))
    difficulty: str = Field(default="medium", max_length=8)

    # 题目数组，结构见 docs/db.md §4.1
    question_data: list[dict] = Field(default_factory=list, sa_type=JSONB)

    model: str = Field(max_length=64)
    prompt_tokens: int = Field(default=0, sa_type=Integer)
    completion_tokens: int = Field(default=0, sa_type=Integer)
    latency_ms: int | None = Field(default=None, sa_type=Integer)

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class QuizAttempt(SQLModel, table=True):
    """答卷：**不软删除** —— 它是统计与推荐的依据（docs/db.md §3.10）。"""

    __tablename__ = "quiz_attempt"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_attempt_score"),
        Index("ix_attempt_quiz_created", "quiz_id", "created_at"),
        Index("ix_attempt_user_created", "user_id", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    quiz_id: uuid.UUID = Field(foreign_key="quiz.id", ondelete="CASCADE", index=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)

    # 用户作答，结构见 docs/db.md §4.2
    answers: list[dict] = Field(default_factory=list, sa_type=JSONB)
    score: Decimal = Field(sa_type=Numeric(5, 2))
    correct_count: int = Field(sa_type=SmallInteger)
    question_count: int = Field(sa_type=SmallInteger)
    duration_seconds: int | None = Field(default=None, sa_type=Integer)

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
