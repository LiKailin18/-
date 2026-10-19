"""FastAPI 依赖：数据库会话、当前用户、当前管理员。

权限设计的三条规则（CLAUDE.md §4）都在这里收口：
1. 令牌只带 sub / pv / typ，**角色读库判定**，不信令牌声明
2. `token_version` 不一致即视为已吊销（改密码 / 改角色 / 强制下线）
3. 账号被禁用时返回 403 USER_003（而不是让它继续用旧令牌
"""

import uuid
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountDisabled,
    FeatureDisabled,
    Forbidden,
    InvalidToken,
    TokenExpired,
    Unauthorized,
)
from app.core.security import TokenExpiredError, TokenInvalidError, decode_token
from app.db.session import get_db
from app.models import AppUser
from app.services import user_service

# auto_error=False：未带令牌时走我们自己的错误体（AUTH_001），
# 而不是 FastAPI 默认的 {"detail": "Not authenticated"}
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]
BearerToken = Annotated[str | None, Depends(oauth2_scheme)]


async def load_user_from_payload(db: AsyncSession, payload: dict[str, Any]) -> AppUser:
    """按令牌载荷读库校验：存在性 + token_version + 启用状态。"""
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise InvalidToken from exc

    user = await user_service.get_by_id(db, user_id)
    if user is None:
        raise InvalidToken
    if user.token_version != payload.get("pv"):
        # 改密码 / 改角色 / 强制下线后，所有旧令牌在这里被拒绝
        raise InvalidToken("凭证已失效，请重新登录")
    if not user.is_active:
        raise AccountDisabled(f"账号已被禁用：{user.disabled_reason or '请联系管理员'}")
    return user


async def get_current_user(db: DbSession, token: BearerToken) -> AppUser:
    if not token:
        raise Unauthorized
    try:
        payload = decode_token(token, expected_type="access")
    except TokenExpiredError as exc:
        # AUTH_002：前端只对这个码触发刷新流程
        raise TokenExpired from exc
    except TokenInvalidError as exc:
        raise InvalidToken from exc
    return await load_user_from_payload(db, payload)


async def get_current_admin(user: Annotated[AppUser, Depends(get_current_user)]) -> AppUser:
    """管理端依赖（功能 13）。M1 先写好，避免 M6b 再动鉴权层。"""
    if user.role != "admin":
        raise Forbidden
    return user


CurrentUser = Annotated[AppUser, Depends(get_current_user)]
CurrentAdmin = Annotated[AppUser, Depends(get_current_admin)]


async def get_ai_enabled(db: DbSession) -> None:
    """AI 总开关（功能 13.5 的生效点）。

    作为 `/api/v1/ai/*` 的路由级依赖：关掉后整组接口 503，
    前端据此把 AI 入口置灰并提示「AI 功能已暂停」。
    答卷判分（`/quizzes/{id}/attempts`）不在这一组里 —— 它不调用模型，不该被关掉。
    """
    from app.services import setting_service

    if not await setting_service.is_enabled(db, "ai.enabled"):
        raise FeatureDisabled("AI 功能已暂停，请联系管理员")


AiEnabled = Annotated[None, Depends(get_ai_enabled)]


class PaginationParams:
    """统一分页参数：?page=1&size=20（size 上限 100）。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        size: int = Query(20, ge=1, le=100, description="每页数量，上限 100"),
    ) -> None:
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


PageParams = Annotated[PaginationParams, Depends()]
