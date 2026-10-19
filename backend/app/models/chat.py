"""AI 问答的表模型：会话与消息（docs/db.md §3.7、§3.8）。

约定：`tool` / `system` 角色的中间消息**不落库**，只在流式过程中作为事件推送。
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.user import utcnow

MESSAGE_ROLES = ("user", "assistant")


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_session"
    __table_args__ = (
        Index(
            "ix_session_user_last",
            "user_id",
            "last_message_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)
    material_id: uuid.UUID | None = Field(
        default=None, foreign_key="material.id", ondelete="SET NULL"
    )

    title: str = Field(default="新会话", max_length=200)
    # 冗余计数：列表页就不用为每个会话做一次聚合
    message_count: int = Field(default=0, sa_type=Integer)
    last_message_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        Index("ix_msg_session_created", "session_id", "created_at"),
        Index("ix_msg_user", "user_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="chat_session.id", ondelete="CASCADE", index=True)
    # 冗余 user_id：便于越权校验与后续统计
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)

    role: str = Field(max_length=16)
    content: str = Field(sa_type=Text)
    # 该轮实际调用了哪些工具，供演示与调试（[{name, args}]）
    tool_calls: list[dict] | None = Field(default=None, sa_type=JSONB)

    prompt_tokens: int = Field(default=0, sa_type=Integer)
    completion_tokens: int = Field(default=0, sa_type=Integer)
    latency_ms: int | None = Field(default=None, sa_type=Integer)

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
