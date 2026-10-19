"""管理端两张表（docs/db.md §3.13 / §3.14）。

- `app_setting`：可调系统配置。用 KV 而不是单行宽表，加配置不用改结构
- `admin_audit_log`：管理员操作审计。**只增不改不删**

为什么功能 13 只加这两张表：用户 / 资料 / 笔记 / 测试题 / AI 用量都是
「对已有表的跨用户读写」，不需要新表；真正新增的只有「可调配置」与「审计」。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlmodel import Field, SQLModel

from app.models.user import utcnow

SETTING_VALUE_TYPES = ("int", "bool", "string", "json")
AUDIT_TARGET_TYPES = ("user", "material", "note", "quiz", "setting", "system")


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_setting"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('int', 'bool', 'string', 'json')", name="ck_setting_value_type"
        ),
    )

    key: str = Field(max_length=64, primary_key=True)
    # 标量也包在 JSONB 里（int / bool / string 统一存法），value_type 供前端渲染表单
    value: Any = Field(sa_type=JSONB)
    value_type: str = Field(max_length=16)
    description: str = Field(max_length=200, sa_type=Text)

    updated_by: uuid.UUID | None = Field(
        default=None, foreign_key="app_user.id", ondelete="SET NULL"
    )
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class AdminAuditLog(SQLModel, table=True):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('user', 'material', 'note', 'quiz', 'setting', 'system')",
            name="ck_audit_target_type",
        ),
        Index("idx_audit_created", text("created_at DESC")),
        Index("idx_audit_admin_created", "admin_id", text("created_at DESC")),
        Index("idx_audit_target", "target_type", "target_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # 管理员被禁用/删除也不影响历史日志的可读性，所以只在物理删除时 SET NULL
    admin_id: uuid.UUID | None = Field(
        default=None, foreign_key="app_user.id", ondelete="SET NULL"
    )

    action: str = Field(max_length=48)
    target_type: str = Field(max_length=24)
    target_id: uuid.UUID | None = Field(default=None)

    # 变更前后快照，如 {"from": {"is_active": true}, "to": {"is_active": false}}
    detail: dict = Field(default_factory=dict, sa_type=JSONB)

    ip: str | None = Field(default=None, sa_type=INET)
    user_agent: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
