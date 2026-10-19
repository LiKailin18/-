"""管理端用户管理（功能 13.2；契约：docs/api.md §16.2）。

安全规则都在 `admin_user_service` 里收口，这里只做参数校验与事务提交。
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Query, Request, status

from app.core.deps import CurrentAdmin, DbSession, PageParams
from app.core.openapi import ERR_400, ERR_404
from app.schemas.admin import (
    AdminUserDetailOut,
    AdminUserItemOut,
    AdminUserPage,
    AdminUserUpdateIn,
    ResetPasswordOut,
)
from app.services import admin_user_service

router = APIRouter(prefix="/users", tags=["管理端 · 用户管理"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


@router.get("", summary="用户列表", response_model=AdminUserPage)
async def list_users(
    _admin: CurrentAdmin,
    db: DbSession,
    page: PageParams,
    keyword: str | None = Query(default=None, description="用户名 / 邮箱 / 昵称模糊匹配"),
    role: Literal["user", "admin"] | None = None,
    is_active: bool | None = None,
    order: str = Query(
        default="-created_at",
        description="排序：-created_at / username / -last_login_at",
    ),
) -> AdminUserPage:
    items, total = await admin_user_service.list_users(
        db,
        offset=page.offset,
        limit=page.size,
        keyword=keyword,
        role=role,
        is_active=is_active,
        order=order,
    )
    return AdminUserPage(
        items=[AdminUserItemOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.get(
    "/{user_id}",
    summary="用户详情",
    response_model=AdminUserDetailOut,
    responses={status.HTTP_404_NOT_FOUND: ERR_404},
)
async def get_user(user_id: uuid.UUID, _admin: CurrentAdmin, db: DbSession) -> AdminUserDetailOut:
    data = await admin_user_service.get_detail(db, user_id)
    return AdminUserDetailOut.model_validate(data)


@router.patch(
    "/{user_id}",
    summary="修改用户（启用/禁用/角色）",
    response_model=AdminUserDetailOut,
    responses={
        status.HTTP_400_BAD_REQUEST: ERR_400,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdateIn,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
) -> AdminUserDetailOut:
    """三条规则：禁止操作自己（400 ADMIN_001）、变更即下线、禁用必填原因。"""
    ip, user_agent = _client_meta(request)
    await admin_user_service.update_user(
        db,
        admin=admin,
        user_id=user_id,
        is_active=payload.is_active,
        role=payload.role,
        disabled_reason=payload.disabled_reason,
        ip=ip,
        user_agent=user_agent,
    )
    await db.commit()  # 业务变更与审计日志同一个事务
    return AdminUserDetailOut.model_validate(await admin_user_service.get_detail(db, user_id))


@router.post(
    "/{user_id}/reset-password",
    summary="重置密码（返回一次性临时密码）",
    response_model=ResetPasswordOut,
    responses={
        status.HTTP_400_BAD_REQUEST: ERR_400,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)
async def reset_password(
    user_id: uuid.UUID,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
) -> ResetPasswordOut:
    ip, user_agent = _client_meta(request)
    password = await admin_user_service.reset_password(
        db, admin=admin, user_id=user_id, ip=ip, user_agent=user_agent
    )
    await db.commit()
    return ResetPasswordOut(
        temporary_password=password,
        note="请线下告知用户；该密码只在本次响应中出现，首次登录后建议修改",
    )


@router.post(
    "/{user_id}/revoke-tokens",
    summary="强制下线",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_400_BAD_REQUEST: ERR_400,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)
async def revoke_tokens(
    user_id: uuid.UUID,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
) -> None:
    ip, user_agent = _client_meta(request)
    await admin_user_service.revoke_tokens(
        db, admin=admin, user_id=user_id, ip=ip, user_agent=user_agent
    )
    await db.commit()
