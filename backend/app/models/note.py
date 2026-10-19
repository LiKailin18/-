"""在线笔记表模型（docs/db.md §3.3）。

内容上限 100000 字（应用层校验）；列表接口只返回 excerpt，不返回正文。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from app.models.user import utcnow


class Note(SQLModel, table=True):
    __tablename__ = "note"
    __table_args__ = (
        Index(
            "ix_note_user_updated",
            "user_id",
            "updated_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_note_tags", "tags", postgresql_using="gin"),
        # 标题与正文的模糊搜索都走 pg_trgm（中文分词不可用的替代方案）
        Index(
            "ix_note_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_note_content_trgm",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)
    # 关联资料被删除时把外键置空，笔记本身保留（docs/db.md §3.3）
    material_id: uuid.UUID | None = Field(
        default=None, foreign_key="material.id", ondelete="SET NULL", index=True
    )

    title: str = Field(max_length=200)
    content: str = Field(default="", sa_type=Text)
    tags: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
