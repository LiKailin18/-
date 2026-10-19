"""用户相关的请求/响应模型（契约：docs/api.md §4）。

响应模型一律显式声明字段，不复用表模型 —— 否则 password_hash 之类会被意外暴露
（CLAUDE.md §5.1）。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,32}$"


def _validate_password_strength(value: str) -> str:
    """契约要求：≥8 位且同时包含字母与数字。"""
    if not any(ch.isalpha() for ch in value):
        raise ValueError("密码需包含字母")
    if not any(ch.isdigit() for ch in value):
        raise ValueError("密码需包含数字")
    return value


class UserCreate(BaseModel):
    """注册入参。"""

    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserOut(BaseModel):
    """用户信息出参 —— 字段与 docs/api.md §4 严格一致。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    nickname: str | None
    avatar_url: str | None
    learning_goal: str | None
    daily_target_minutes: int
    role: str
    created_at: datetime


class UserUpdate(BaseModel):
    """PATCH /users/me：只提交要改的字段（未提交的字段不变）。"""

    email: EmailStr | None = None
    nickname: str | None = Field(default=None, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=512)
    learning_goal: str | None = Field(default=None, max_length=200)
    daily_target_minutes: int | None = Field(default=None, ge=1, le=1440)


class PasswordChangeIn(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, value: str) -> str:
        return _validate_password_strength(value)
