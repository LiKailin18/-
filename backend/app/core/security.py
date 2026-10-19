"""密码哈希与 JWT 签发/校验。

纯逻辑层：不依赖数据库、不依赖 FastAPI（CLAUDE.md §5.1）。
令牌载荷只用三个字段（CLAUDE.md §4）：sub(用户 ID) / pv(token_version) / typ(类型)。
**角色不进令牌** —— 每次鉴权读库判定，token 泄露后也能立刻降权。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

TokenType = Literal["access", "refresh"]

# Argon2id（pwdlib 推荐的参数组合）
_password_hasher = PasswordHash.recommended()


class TokenExpiredError(Exception):
    """令牌过期 —— 对应 AUTH_002，前端据此触发 refresh 流程。"""


class TokenInvalidError(Exception):
    """令牌无效：签名错误、类型不符、字段缺失、算法不符 —— 对应 AUTH_003。"""


# --------------------------------------------------------------------------- 密码


def hash_password(raw_password: str) -> str:
    return _password_hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(raw_password, password_hash)
    except Exception:
        # 不向上抛：数据库里的脏哈希不应该让登录接口 500，也不该泄露内部信息
        return False


# --------------------------------------------------------------------------- JWT


def create_token(*, user_id: uuid.UUID, token_version: int, token_type: TokenType) -> str:
    """签发 access / refresh 令牌。"""
    now = datetime.now(UTC)
    if token_type == "access":
        expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expires_at = now + timedelta(days=settings.refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "pv": token_version,
        "typ": token_type,
        # jti：同一秒内签发的令牌也必须互不相同（否则 refresh 的「轮换」无法验证）
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """解析并校验令牌。

    过期的抛 TokenExpiredError（前端要刷新），其余问题抛 TokenInvalidError。
    这个区分是契约要求（AUTH_002 vs AUTH_003），前端只对前者触发刷新。
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError from exc

    if payload.get("typ") != expected_type:
        raise TokenInvalidError(f"令牌类型不符，期望 {expected_type}")
    if not payload.get("sub") or payload.get("pv") is None:
        raise TokenInvalidError("令牌缺少必要字段")
    return payload
