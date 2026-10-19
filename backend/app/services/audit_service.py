"""管理端操作审计（功能 13.5；契约：docs/api.md §16.6 / docs/db.md §3.14）。

铁律：**审计与业务变更在同一个事务里提交**（`write_log` 只 `db.add`，不 commit），
否则会出现「改了但没记」。调用方负责 `await db.commit()`。

审计日志只增不改不删，管理端不提供删除接口。
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog, AppUser

# action 常量（docs/db.md §3.14 的表，应用层常量而非 CHECK 枚举，便于扩展）
ACTION_USER_DISABLE = "user.disable"
ACTION_USER_ENABLE = "user.enable"
ACTION_USER_ROLE_CHANGE = "user.role_change"
ACTION_USER_RESET_PASSWORD = "user.reset_password"
ACTION_USER_REVOKE_TOKENS = "user.revoke_tokens"
ACTION_MATERIAL_DELETE = "material.delete"
ACTION_MATERIAL_REPARSE = "material.reparse"
ACTION_NOTE_DELETE = "note.delete"
ACTION_QUIZ_DELETE = "quiz.delete"
ACTION_SETTING_UPDATE = "setting.update"

ACTIONS = (
    ACTION_USER_DISABLE,
    ACTION_USER_ENABLE,
    ACTION_USER_ROLE_CHANGE,
    ACTION_USER_RESET_PASSWORD,
    ACTION_USER_REVOKE_TOKENS,
    ACTION_MATERIAL_DELETE,
    ACTION_MATERIAL_REPARSE,
    ACTION_NOTE_DELETE,
    ACTION_QUIZ_DELETE,
    ACTION_SETTING_UPDATE,
)


def write_log(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AdminAuditLog:
    """登记一条审计日志（**不 commit**，与业务变更同事务）。"""
    row = AdminAuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip=ip,
        user_agent=user_agent[:255] if user_agent else None,
    )
    db.add(row)
    return row


async def list_logs(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
    admin_id: uuid.UUID | None = None,
    action: str | None = None,
    target_type: str | None = None,
    date_from: Any = None,
    date_to: Any = None,
) -> tuple[list[dict], int]:
    """审计日志列表（含操作人用户名）。"""
    conditions = []
    if admin_id:
        conditions.append(AdminAuditLog.admin_id == admin_id)
    if action:
        conditions.append(AdminAuditLog.action == action)
    if target_type:
        conditions.append(AdminAuditLog.target_type == target_type)
    if date_from:
        conditions.append(func.date(AdminAuditLog.created_at) >= date_from)
    if date_to:
        conditions.append(func.date(AdminAuditLog.created_at) <= date_to)

    total = await db.scalar(
        select(func.count()).select_from(AdminAuditLog).where(*conditions)
    )
    rows = (
        await db.execute(
            select(AdminAuditLog, AppUser.username)
            .join(AppUser, AppUser.id == AdminAuditLog.admin_id, isouter=True)
            .where(*conditions)
            .order_by(AdminAuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [
        {
            "id": row.AdminAuditLog.id,
            "admin": (
                {"id": row.AdminAuditLog.admin_id, "username": row.username}
                if row.AdminAuditLog.admin_id
                else None
            ),
            "action": row.AdminAuditLog.action,
            "target_type": row.AdminAuditLog.target_type,
            "target_id": row.AdminAuditLog.target_id,
            "detail": row.AdminAuditLog.detail,
            "ip": str(row.AdminAuditLog.ip) if row.AdminAuditLog.ip else None,
            "created_at": row.AdminAuditLog.created_at,
        }
        for row in rows
    ]
    return items, int(total or 0)
