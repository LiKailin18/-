"""学习资料相关模型（契约：docs/api.md §5）。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.text import normalize_tags

ParseStatus = Literal["pending", "parsing", "success", "failed", "unsupported"]


class MaterialOut(BaseModel):
    """资料的出参 —— **不含 extracted_text / file_path**（CLAUDE.md §7）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    subject: str | None
    tags: list[str]
    file_name: str
    file_ext: str
    mime_type: str
    size_bytes: int
    page_count: int | None
    char_count: int | None
    parse_status: ParseStatus
    parse_error: str | None
    created_at: datetime


class MaterialUpdate(BaseModel):
    """PATCH 语义：只提交要改的字段。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = Field(default=None, max_length=20)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return normalize_tags(value)


class MaterialTextOut(BaseModel):
    """分片读取正文（与 M5 的 agent 工具 read_material_chunk 共用同一 service）。"""

    material_id: uuid.UUID
    offset: int
    limit: int
    total_chars: int
    has_more: bool
    text: str


class AvatarOut(BaseModel):
    avatar_url: str
