"""AI 相关请求/响应模型（契约：docs/api.md §10、§11、§14）。"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SummaryStyle = Literal["outline", "key_points", "detailed"]
AdviceFocus = Literal["review", "plan", "balance"]
QuizTypeFilter = Literal["single", "multiple", "judge", "blank"]


# --------------------------------------------------------------------- 总结


class SummaryCreate(BaseModel):
    material_id: uuid.UUID
    scope_start: int = Field(default=0, ge=0)
    scope_end: int | None = Field(default=None, ge=0)
    style: SummaryStyle = "outline"


class SummaryOut(BaseModel):
    """详情/生成出参：含完整正文。"""

    id: uuid.UUID
    material_id: uuid.UUID | None
    style: SummaryStyle
    mode: Literal["direct", "map_reduce"]
    summary_md: str
    key_points: list[str]
    char_count: int
    segments: int
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int | None
    created_at: datetime


class SummaryBrief(BaseModel):
    """列表出参：**不含 summary_md**（避免列表返回大字段）。"""

    id: uuid.UUID
    material_id: uuid.UUID | None
    style: SummaryStyle
    mode: str
    key_points: list[str]
    char_count: int
    created_at: datetime


# --------------------------------------------------------------------- 测试题


class QuizCreate(BaseModel):
    material_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)
    count: int = Field(default=5, ge=1, le=20)
    types: list[QuizTypeFilter] = Field(default_factory=lambda: ["single"], min_length=1)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    scope_start: int = Field(default=0, ge=0)
    scope_end: int | None = Field(default=None, ge=0)


class QuizQuestionOut(BaseModel):
    no: int
    type: QuizTypeFilter
    stem: str
    options: list[str]
    answer: list[str] | None = None
    explanation: str | None = None
    difficulty: str
    knowledge: str
    source_hint: str | None = None


class QuizOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID | None
    title: str
    question_count: int
    types: list[str]
    difficulty: str
    questions: list[QuizQuestionOut]
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int | None
    created_at: datetime


class QuizBrief(BaseModel):
    """列表出参：不给题目内容（防答案泄露）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID | None
    title: str
    question_count: int
    types: list[str]
    difficulty: str
    created_at: datetime


class QuizAnswerIn(BaseModel):
    no: int = Field(ge=1)
    answer: list[str] = Field(default_factory=list)


class QuizAttemptCreate(BaseModel):
    answers: list[QuizAnswerIn] = Field(min_length=1)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)


class AttemptDetail(BaseModel):
    no: int
    your_answer: list[str]
    correct_answer: list[str]
    is_correct: bool
    explanation: str | None = None


class QuizAttemptOut(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    score: float
    correct_count: int
    question_count: int
    duration_seconds: int | None
    created_at: datetime
    details: list[AttemptDetail] = Field(default_factory=list)


# --------------------------------------------------------------------- 学习建议


class AdviceGenerateIn(BaseModel):
    days: int = Field(default=7, ge=1, le=90)
    focus: AdviceFocus = "review"


class AdviceSuggestionOut(BaseModel):
    title: str
    reason: str
    action: str
    priority: str


class AdviceOut(BaseModel):
    id: uuid.UUID
    period_days: int
    focus: AdviceFocus
    summary: str
    suggestions: list[AdviceSuggestionOut]
    weak_points: list[dict]
    next_7_days: list[dict]
    stale: bool = False
    model: str
    latency_ms: int | None
    created_at: datetime


class AdviceBrief(BaseModel):
    id: uuid.UUID
    period_days: int
    focus: str
    summary: str
    created_at: datetime


class AdviceLatestOut(BaseModel):
    """GET /ai/advice：可能没有记录，所以 advice 允许为空。"""

    advice: AdviceOut | None = None
    stale: bool = False


# --------------------------------------------------------------------- 用量


class UsageDailyItem(BaseModel):
    date: date
    calls: int
    total_tokens: int


class UsageOut(BaseModel):
    days: int
    today_calls: int
    daily_quota: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    success_rate: float
    items: list[UsageDailyItem] = Field(default_factory=list)


# --------------------------------------------------------------------- 问答


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    material_id: uuid.UUID | None = None


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    material_id: uuid.UUID | None
    message_count: int
    last_message_at: datetime | None
    created_at: datetime


class ChatAskIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    material_id: uuid.UUID | None = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    tool_calls: list[dict] | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int | None
    created_at: datetime


class ChatAnswerOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"] = "assistant"
    content: str
    tool_calls: list[dict] = Field(default_factory=list)
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int | None
    created_at: datetime
