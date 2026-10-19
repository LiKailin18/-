"""学习计划模型（契约：docs/api.md §7）。"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PlanStatus = Literal["draft", "active", "done", "archived"]

MAX_PLAN_DAYS = 180


class PlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=64)
    goal: str | None = Field(default=None, max_length=500)
    start_date: date
    end_date: date
    daily_minutes: int = Field(default=60, ge=1, le=600)
    material_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    status: PlanStatus = "active"

    @model_validator(mode="after")
    def check_range(self) -> "PlanCreate":
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        if (self.end_date - self.start_date).days > MAX_PLAN_DAYS:
            raise ValueError(f"计划区间不能超过 {MAX_PLAN_DAYS} 天")
        return self


class PlanUpdate(BaseModel):
    """PATCH 语义。

    start_date / end_date 虽然在这里声明，但**不允许修改** ——
    已生成的任务会和区间不一致，接口层会直接返回 400（契约 §7）。
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=64)
    goal: str | None = Field(default=None, max_length=500)
    daily_minutes: int | None = Field(default=None, ge=1, le=600)
    status: PlanStatus | None = None
    material_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)

    start_date: date | None = None
    end_date: date | None = None


class PlanProgress(BaseModel):
    task_total: int = 0
    task_done: int = 0
    progress: float = 0.0


class MaterialBrief(BaseModel):
    """计划详情里引用的资料（只给最小字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    subject: str | None


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    subject: str | None
    goal: str | None
    start_date: date
    end_date: date
    daily_minutes: int
    status: PlanStatus
    material_ids: list[uuid.UUID]
    created_at: datetime
    progress: PlanProgress = PlanProgress()


class PlanDetailOut(PlanOut):
    materials: list[MaterialBrief] = Field(default_factory=list)


class GenerateTasksIn(BaseModel):
    overwrite: bool = False


class GenerateTasksOut(BaseModel):
    plan_id: uuid.UUID
    created: int
    skipped: int
    dates: list[date]
