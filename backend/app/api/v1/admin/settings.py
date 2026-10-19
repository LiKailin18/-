"""管理端系统配置接口（功能 13.5；契约：docs/api.md §16.5）。"""

from fastapi import APIRouter, Request, status

from app.core.deps import CurrentAdmin, DbSession
from app.core.openapi import ERR_400
from app.schemas.admin import SettingItemOut, SettingsOut, SettingsUpdateIn
from app.services import audit_service, setting_service

router = APIRouter(prefix="/settings", tags=["管理端 · 系统配置"])


@router.get("", summary="配置列表", response_model=SettingsOut)
async def list_settings(_admin: CurrentAdmin, db: DbSession) -> SettingsOut:
    items = await setting_service.list_settings(db)
    return SettingsOut(items=[SettingItemOut.model_validate(item) for item in items])


@router.patch(
    "",
    summary="批量修改配置",
    response_model=SettingsOut,
    responses={status.HTTP_400_BAD_REQUEST: ERR_400},
)
async def update_settings(
    payload: SettingsUpdateIn, admin: CurrentAdmin, db: DbSession, request: Request
) -> SettingsOut:
    """写入后立即清缓存（下一个请求就生效），并与审计日志同事务提交。"""
    changes = [(item.key, item.value) for item in payload.items]
    snapshot = await setting_service.update_settings(db, admin=admin, changes=changes)

    audit_service.write_log(
        db,
        admin_id=admin.id,
        action=audit_service.ACTION_SETTING_UPDATE,
        target_type="setting",
        detail={"changes": snapshot},
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()

    items = await setting_service.list_settings(db)
    return SettingsOut(items=[SettingItemOut.model_validate(item) for item in items])
