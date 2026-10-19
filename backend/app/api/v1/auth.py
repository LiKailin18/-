"""认证接口（契约：docs/api.md §3）—— 功能 1。

本模块只做编排：解析入参、读写 Cookie、组装响应。
密码校验、冲突判断、token_version 变更都在 services/user_service 里。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.deps import DbSession, load_user_from_payload
from app.core.exceptions import (
    CsrfRejected,
    FeatureDisabled,
    InvalidToken,
    TokenExpired,
    Unauthorized,
)
from app.core.openapi import ERR_401, ERR_403, ERR_409, ERR_503
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_token,
    decode_token,
)
from app.schemas.auth import TokenOut
from app.schemas.user import UserCreate, UserOut
from app.services import setting_service, user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["认证"])

# ------------------------------------------------------------------ Cookie 与 CSRF


def _set_refresh_cookie(response: Response, token: str) -> None:
    """refresh token 只放 httpOnly Cookie，不进响应体（避免被 JS 读到）。"""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "prod",
        path=settings.refresh_cookie_path,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
    )


def _assert_trusted_origin(request: Request) -> None:
    """Cookie 凭证接口的 CSRF 防护（契约 §1.5）。

    浏览器发起的跨站请求一定带 Origin；不带 Origin 的都是非浏览器客户端
    （curl / pytest / 服务端调用），放行即可。
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin not in settings.cors_origin_list:
        logger.warning("CSRF 校验失败，Origin=%s", origin)
        raise CsrfRejected


def _issue_tokens(user) -> tuple[str, str]:
    access = create_token(
        user_id=user.id, token_version=user.token_version, token_type="access"
    )
    refresh = create_token(
        user_id=user.id, token_version=user.token_version, token_type="refresh"
    )
    return access, refresh


# ------------------------------------------------------------------ 接口


@router.post(
    "/register",
    summary="注册",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    responses={
        status.HTTP_409_CONFLICT: ERR_409,
        status.HTTP_503_SERVICE_UNAVAILABLE: ERR_503,
    },
)
async def register(payload: UserCreate, db: DbSession) -> UserOut:
    """注册成功**不自动登录**，前端随后调用 /auth/login（契约 §3）。

    管理端可以关闭注册（`register.allow=false` → 503 SYS_503，契约 §16.5）。
    """
    if not await setting_service.is_enabled(db, "register.allow"):
        raise FeatureDisabled("注册功能已关闭，请联系管理员")
    user = await user_service.create_user(db, payload)
    return UserOut.model_validate(user)


@router.post(
    "/login",
    summary="登录",
    response_model=TokenOut,
    responses={status.HTTP_401_UNAUTHORIZED: ERR_401, status.HTTP_403_FORBIDDEN: ERR_403},
)
async def login(
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenOut:
    """表单格式（OAuth2 规范），字段名固定为 username / password。"""
    user = await user_service.authenticate(db, form.username, form.password)
    access, refresh = _issue_tokens(user)
    _set_refresh_cookie(response, refresh)
    return TokenOut(
        access_token=access,
        expires_in=settings.access_token_expire_minutes * 60,
        role=user.role,
    )


@router.post(
    "/refresh",
    summary="刷新访问令牌",
    response_model=TokenOut,
    responses={status.HTTP_401_UNAUTHORIZED: ERR_401, status.HTTP_403_FORBIDDEN: ERR_403},
)
async def refresh(request: Request, response: Response, db: DbSession) -> TokenOut:
    """只读 Cookie，不接受 body 传令牌，并轮换 refresh Cookie。"""
    _assert_trusted_origin(request)

    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise Unauthorized

    try:
        payload = decode_token(token, expected_type="refresh")
    except TokenExpiredError as exc:
        _clear_refresh_cookie(response)
        raise TokenExpired("登录已过期，请重新登录") from exc
    except TokenInvalidError as exc:
        _clear_refresh_cookie(response)
        raise InvalidToken from exc

    user = await load_user_from_payload(db, payload)
    access, new_refresh = _issue_tokens(user)
    _set_refresh_cookie(response, new_refresh)
    return TokenOut(
        access_token=access,
        expires_in=settings.access_token_expire_minutes * 60,
        role=user.role,
    )


@router.post(
    "/logout",
    summary="登出",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_403_FORBIDDEN: ERR_403},
)
async def logout(request: Request, response: Response) -> None:
    """清 Cookie。幂等：没带 Cookie 也返回 204。"""
    _assert_trusted_origin(request)
    _clear_refresh_cookie(response)
