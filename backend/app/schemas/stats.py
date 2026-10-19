"""统计与个性化推荐的出参模型（契约：docs/api.md §12）。

字段名与 `stats_service` 的返回键一一对应，api 层只做装配、不重算。
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StatsPeriodOut(BaseModel):
    """统计窗口。`from` 是 Python 保留字，所以字段名用 date_from + 别名。"""

    model_config = ConfigDict(populate_by_name=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    days: int


class StatsOverviewOut(BaseModel):
    period: StatsPeriodOut
    total_minutes: int
    active_days: int
    streak_days: int
    daily_avg_minutes: float
    task_total: int
    task_done: int
    task_completion_rate: float
    quiz_attempts: int
    quiz_accuracy: float
    materials: int
    notes: int
    ai_calls: int


class StatsDailyItem(BaseModel):
    date: date
    minutes: int
    task_total: int
    task_done: int
    quiz_attempts: int
    quiz_accuracy: float


class StatsDailyOut(BaseModel):
    items: list[StatsDailyItem]


class SubjectStatItem(BaseModel):
    subject: str
    minutes: int
    task_done: int


class StatsSubjectsOut(BaseModel):
    items: list[SubjectStatItem]


class WeakPointItem(BaseModel):
    knowledge: str
    attempts: int
    correct: int
    accuracy: float


class WeakPointsOut(BaseModel):
    items: list[WeakPointItem]


RecommendationKind = Literal["task", "review", "plan", "material", "habit"]


class RecommendationItem(BaseModel):
    kind: RecommendationKind
    priority: int
    title: str
    reason: str
    action: str
    route: str
    ref_id: str | None = None


class RecommendationsOut(BaseModel):
    generated_at: datetime
    items: list[RecommendationItem]
