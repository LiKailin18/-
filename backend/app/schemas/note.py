"""笔记相关模型（契约：docs/api.md §6）。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.text import normalize_tags

CONTENT_MAX_LENGTH = 100_000


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=CONTENT_MAX_LENGTH)
    tags: list[str] = Field(default_factory=list, max_length=20)
    material_id: uuid.UUID | None = None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value) or []


class NoteUpdate(BaseModel):
    """PATCH 语义：只提交要改的字段。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=CONTENT_MAX_LENGTH)
    tags: list[str] | None = Field(default=None, max_length=20)
    material_id: uuid.UUID | None = None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return normalize_tags(value)


class NoteOut(BaseModel):
    """详情出参：含完整正文。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    tags: list[str]
    material_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class NoteListItem(BaseModel):
    """列表出参：**不含正文**，只给 excerpt（契约 §6）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    excerpt: str
    tags: list[str]
    material_id: uuid.UUID | None
    updated_at: datetime
