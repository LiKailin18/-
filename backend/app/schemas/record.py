"""学习记录模型（契约：docs/api.md §9）。"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RecordType = Literal["reading", "video", "practice", "review", "other"]

# 允许轻微时差（客户端时钟可能快几分钟）
FUTURE_TOLERANCE = timedelta(minutes=5)


class RecordCreate(BaseModel):
    task_id: uuid.UUID | None = None
    material_id: uuid.UUID | None = None
    type: RecordType = "reading"
    started_at: datetime
    duration_minutes: int = Field(ge=1, le=1440)
    content: str | None = Field(default=None, max_length=500)

    @field_validator("started_at")
    @classmethod
    def not_in_future(cls, value: datetime) -> datetime:
        """契约：开始时间不允许晚于当前时间 +5 分钟（防止乱填影响统计）。"""
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        if moment > datetime.now(UTC) + FUTURE_TOLERANCE:
            raise ValueError("学习开始时间不能晚于当前时间")
        return moment


class RecordUpdate(BaseModel):
    type: RecordType | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    content: str | None = Field(default=None, max_length=500)
    started_at: datetime | None = None

    @field_validator("started_at")
    @classmethod
    def not_in_future(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        if moment > datetime.now(UTC) + FUTURE_TOLERANCE:
            raise ValueError("学习开始时间不能晚于当前时间")
        return moment


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID | None
    material_id: uuid.UUID | None
    type: RecordType
    started_at: datetime
    duration_minutes: int
    content: str | None
    created_at: datetime
