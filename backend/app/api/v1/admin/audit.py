"""管理端操作审计接口（功能 13.5；契约：docs/api.md §16.6）。

审计日志**只读**：没有删除/修改接口（只增不改不删）。
"""

import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.core.deps import CurrentAdmin, DbSession, PageParams
from app.schemas.admin import AuditLogOut, AuditLogPage
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["管理端 · 操作审计"])


@router.get("", summary="审计日志", response_model=AuditLogPage)
async def list_audit_logs(
    _admin: CurrentAdmin,
    db: DbSession,
    page: PageParams,
    admin_id: uuid.UUID | None = None,
    action: str | None = Query(default=None, description="如 user.disable"),
    target_type: str | None = Query(default=None, description="user/material/note/quiz/setting"),
    date_from: date | None = None,
    date_to: date | None = None,
) -> AuditLogPage:
    items, total = await audit_service.list_logs(
        db,
        offset=page.offset,
        limit=page.size,
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        date_from=date_from,
        date_to=date_to,
    )
    return AuditLogPage(
        items=[AuditLogOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )
