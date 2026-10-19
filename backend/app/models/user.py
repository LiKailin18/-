"""用户表模型（docs/db.md §3.1）。

字段、长度、约束都按契约写；改动前先改 docs/db.md。
枚举一律用 VARCHAR + CHECK，不用 PG 原生 ENUM（CLAUDE.md §6）。

注意：这里**不用** `from __future__ import annotations`。
SQLModel 需要在类创建时拿到真实类型对象来做字段映射，字符串化注解在部分
场景下会解析失败；Python 3.12 本身已支持 `str | None` 写法。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """带时区的 UTC 当前时间 —— 存储层统一 UTC（CLAUDE.md §6）。"""
    return datetime.now(UTC)


class AppUser(SQLModel, table=True):
    """用户。表名用 app_user 而不是 user：user 是 SQL 保留字。"""

    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(
            "daily_target_minutes BETWEEN 1 AND 1440", name="ck_user_daily_target_minutes"
        ),
        CheckConstraint("role IN ('user', 'admin')", name="ck_user_role"),
        # 管理端用户列表要按角色 + 启用状态筛选
        Index("ix_user_role_is_active", "role", "is_active"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    username: str = Field(max_length=32, unique=True, index=True)
    email: str = Field(max_length=254, unique=True, index=True)
    password_hash: str = Field(max_length=255)

    nickname: str | None = Field(default=None, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=512)
    learning_goal: str | None = Field(default=None, max_length=200)
    daily_target_minutes: int = Field(default=60, sa_type=SmallInteger)

    role: str = Field(default="user", max_length=16)
    is_active: bool = Field(default=True)
    disabled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    disabled_reason: str | None = Field(default=None, max_length=200)

    # JWT 里带 pv；改密码 / 改角色 / 强制下线时 +1，旧令牌立即全体失效
    token_version: int = Field(default=0, sa_type=SmallInteger)

    last_login_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
