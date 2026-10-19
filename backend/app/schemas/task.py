"""学习任务模型（契约：docs/api.md §8）。"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["pending", "doing", "done", "skipped"]


class TaskCreate(BaseModel):
    """手工建任务（允许不挂计划）。"""

    plan_id: uuid.UUID | None = None
    plan_date: date
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    est_minutes: int = Field(default=30, ge=1, le=600)
    material_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    est_minutes: int | None = Field(default=None, ge=1, le=600)
    status: TaskStatus | None = None
    plan_date: date | None = None
    material_id: uuid.UUID | None = None


class TaskCompleteIn(BaseModel):
    """完成任务。

    create_record=True 时会在**同一事务**里写一条 study_record（契约 §8）。
    """

    duration_minutes: int = Field(default=30, ge=1, le=1440)
    content: str | None = Field(default=None, max_length=500)
    create_record: bool = True


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID | None
    plan_date: date
    title: str
    description: str | None
    order_no: int
    est_minutes: int
    status: TaskStatus
    completed_at: datetime | None
    material_id: uuid.UUID | None


class TaskCompleteOut(BaseModel):
    task: TaskOut
    study_record_id: uuid.UUID | None
