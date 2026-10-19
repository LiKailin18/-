"""管理端出参与入参（契约：docs/api.md §16）。

只有管理端用的模型放这里；用户端能复用的（如 `MaterialOut`）仍从各自模块取。
"""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------- 通用


class AdminUserRef(BaseModel):
    """列表里嵌的「归属用户」，只给 id + username（最小必要信息）。"""

    id: uuid.UUID
    username: str


# --------------------------------------------------------------------- 13.5 系统配置


class SettingItemOut(BaseModel):
    key: str
    value: Any
    value_type: Literal["int", "bool", "string", "json"]
    description: str
    editable: bool
    updated_at: datetime | None = None
    updated_by_username: str | None = None


class SettingsOut(BaseModel):
    items: list[SettingItemOut]


class SettingUpdateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    value: Any


class SettingsUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SettingUpdateItem] = Field(min_length=1, max_length=20)


# --------------------------------------------------------------------- 13.5 审计


class AuditLogOut(BaseModel):
    id: uuid.UUID
    admin: AdminUserRef | None = None
    action: str
    target_type: str
    target_id: uuid.UUID | None = None
    detail: dict
    ip: str | None = None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    size: int


# --------------------------------------------------------------------- 13.1 仪表盘


class AdminRangeOut(BaseModel):
    """`from`/`to` 是 Python 关键字，字段名用 date_* + 别名。"""

    model_config = ConfigDict(populate_by_name=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    days: int


class AdminUserStatsOut(BaseModel):
    total: int
    active_7d: int
    new_7d: int
    disabled: int
    admins: int


class AdminContentStatsOut(BaseModel):
    materials: int
    notes: int
    plans: int
    quizzes: int


class AdminActivityStatsOut(BaseModel):
    study_minutes: int
    task_completion_rate: float


class AdminAiSummaryOut(BaseModel):
    calls: int
    total_tokens: int
    success_rate: float
    today_calls: int


class AdminOverviewOut(BaseModel):
    range: AdminRangeOut
    users: AdminUserStatsOut
    content: AdminContentStatsOut
    activity: AdminActivityStatsOut
    ai: AdminAiSummaryOut


class AdminDailyItemOut(BaseModel):
    date: date
    new_users: int
    active_users: int
    study_minutes: int
    ai_calls: int


class AdminDailyOut(BaseModel):
    items: list[AdminDailyItemOut]


# --------------------------------------------------------------------- 13.4 AI 用量


class SceneStatOut(BaseModel):
    scene: str
    calls: int
    total_tokens: int
    success_rate: float
    avg_latency_ms: int


class TopUserOut(BaseModel):
    user_id: uuid.UUID
    username: str
    calls: int
    total_tokens: int


class AdminAiDailyOut(BaseModel):
    date: date
    calls: int
    total_tokens: int
    failed: int


class AdminAiStatsOut(BaseModel):
    by_scene: list[SceneStatOut]
    top_users: list[TopUserOut]
    daily: list[AdminAiDailyOut]


class AiUsageItemOut(BaseModel):
    id: uuid.UUID
    user: AdminUserRef
    scene: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    steps: int
    latency_ms: int | None = None
    ok: bool
    error_code: str | None = None
    created_at: datetime


class AiUsagePage(BaseModel):
    items: list[AiUsageItemOut]
    total: int
    page: int
    size: int


# --------------------------------------------------------------------- 13.2 用户管理


class AdminUserCountsOut(BaseModel):
    materials: int
    notes: int
    ai_calls_30d: int
    study_minutes_30d: int


class AdminUserItemOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    nickname: str | None = None
    role: Literal["user", "admin"]
    is_active: bool
    disabled_reason: str | None = None
    created_at: datetime
    last_login_at: datetime | None = None
    counts: AdminUserCountsOut


class AdminUserDetailOut(AdminUserItemOut):
    quiz_accuracy_30d: float
    quiz_attempts_30d: int
    ai_tokens_30d: int


class AdminUserPage(BaseModel):
    items: list[AdminUserItemOut]
    total: int
    page: int
    size: int


class AdminUserUpdateIn(BaseModel):
    """三个字段都可选；只提交要改的。禁用时必须带 `disabled_reason`。"""

    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    disabled_reason: str | None = Field(default=None, max_length=200)
    role: Literal["user", "admin"] | None = None


class ResetPasswordOut(BaseModel):
    temporary_password: str
    note: str


# --------------------------------------------------------------------- 13.3 内容管理


class AdminMaterialItemOut(BaseModel):
    id: uuid.UUID
    title: str
    subject: str | None = None
    file_ext: str
    size_bytes: int
    parse_status: str
    char_count: int | None = None
    created_at: datetime
    owner: AdminUserRef


class AdminMaterialPage(BaseModel):
    items: list[AdminMaterialItemOut]
    total: int
    page: int
    size: int


class AdminNoteItemOut(BaseModel):
    """列表**不含** `content`，只给 `excerpt`（契约 §16.3）。"""

    id: uuid.UUID
    title: str
    excerpt: str
    tags: list[str] = Field(default_factory=list)
    material_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    owner: AdminUserRef


class AdminNotePage(BaseModel):
    items: list[AdminNoteItemOut]
    total: int
    page: int
    size: int


class AdminQuizItemOut(BaseModel):
    """列表**不含** `questions`（防答案泄露面）。"""

    id: uuid.UUID
    title: str
    question_count: int
    types: list[str] = Field(default_factory=list)
    difficulty: str
    material_id: uuid.UUID | None = None
    created_at: datetime
    owner: AdminUserRef


class AdminQuizPage(BaseModel):
    items: list[AdminQuizItemOut]
    total: int
    page: int
    size: int
