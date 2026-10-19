"""学习资料表模型（docs/db.md §3.2）。

注意：extracted_text 可能很大，列表接口一律不返回它；
读取正文走 GET /materials/{id}/text 的分片接口（CLAUDE.md §7）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from app.models.user import utcnow

PARSE_STATUSES = ("pending", "parsing", "success", "failed", "unsupported")


class Material(SQLModel, table=True):
    __tablename__ = "material"
    __table_args__ = (
        CheckConstraint(
            "parse_status IN ('pending', 'parsing', 'success', 'failed', 'unsupported')",
            name="ck_material_parse_status",
        ),
        CheckConstraint("file_ext IN ('.pdf', '.docx')", name="ck_material_file_ext"),
        CheckConstraint("size_bytes > 0", name="ck_material_size_positive"),
        # 列表按「本人 + 时间倒序」查，软删除的行不参与
        Index(
            "ix_material_user_created",
            "user_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_material_user_subject",
            "user_id",
            "subject",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_material_tags", "tags", postgresql_using="gin"),
        # 中文模糊搜索用 pg_trgm（docs/db.md §1）
        Index(
            "ix_material_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_material_user_hash", "user_id", "file_hash"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", index=True)

    title: str = Field(max_length=200)
    subject: str | None = Field(default=None, max_length=64)
    tags: list[str] = Field(default_factory=list, sa_type=ARRAY(Text))

    file_name: str = Field(max_length=255)
    file_ext: str = Field(max_length=8)
    mime_type: str = Field(max_length=128)
    size_bytes: int = Field(sa_type=BigInteger)
    file_path: str = Field(max_length=512)
    file_hash: str = Field(max_length=64)

    page_count: int | None = Field(default=None, sa_type=SmallInteger)
    char_count: int | None = Field(default=None)

    # 解析正文：只用于分片读取与 AI 检索，绝不进列表响应
    extracted_text: str | None = Field(default=None, sa_type=Text)

    parse_status: str = Field(default="pending", max_length=16)
    parse_error: str | None = Field(default=None, sa_type=Text)
    parsed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
