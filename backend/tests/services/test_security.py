"""密码哈希与 JWT 的纯逻辑测试（不需要数据库）。"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.schemas.user import UserCreate

# ------------------------------------------------------------------ 密码


def test_password_hash_is_verifiable():
    hashed = hash_password("Test1234!")
    assert hashed != "Test1234!"
    assert verify_password("Test1234!", hashed) is True
    assert verify_password("Wrong1234", hashed) is False


def test_password_hash_is_salted():
    """同一密码两次哈希结果必须不同（Argon2 自带随机盐）。"""
    assert hash_password("Test1234!") != hash_password("Test1234!")


def test_verify_password_tolerates_corrupted_hash():
    """脏哈希不能让登录接口 500，只算校验失败。"""
    assert verify_password("Test1234!", "not-a-valid-hash") is False


def test_password_must_contain_letter_and_digit():
    with pytest.raises(ValidationError):
        UserCreate(username="abc_123", email="a@example.com", password="alllettersonly")
    with pytest.raises(ValidationError):
        UserCreate(username="abc_123", email="a@example.com", password="12345678")


def test_username_pattern_is_enforced():
    with pytest.raises(ValidationError):
        UserCreate(username="ab", email="a@example.com", password="Test1234!")
    with pytest.raises(ValidationError):
        UserCreate(username="has space", email="a@example.com", password="Test1234!")


# ------------------------------------------------------------------ 安全属性


def test_password_hash_uses_argon2id():
    """哈希必须是 Argon2id —— 防止有人把配置换成弱算法而没人发现。"""
    assert hash_password("Test1234!").startswith("$argon2id$")


def test_access_token_payload_has_no_sensitive_fields():
    """令牌里只能有这六个字段：绝不能带邮箱、密码、角色。"""
    token = create_token(user_id=uuid.uuid4(), token_version=0, token_type="access")

    payload = decode_token(token, expected_type="access")

    assert set(payload) == {"sub", "pv", "typ", "jti", "iat", "exp"}


def test_access_token_lifetime_matches_config():
    token = create_token(user_id=uuid.uuid4(), token_version=0, token_type="access")

    payload = decode_token(token, expected_type="access")

    assert payload["exp"] - payload["iat"] == settings.access_token_expire_minutes * 60


def test_refresh_token_lifetime_matches_config():
    token = create_token(user_id=uuid.uuid4(), token_version=0, token_type="refresh")

    payload = decode_token(token, expected_type="refresh")

    assert payload["exp"] - payload["iat"] == settings.refresh_token_expire_days * 86400


# ------------------------------------------------------------------ JWT


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_token(user_id=user_id, token_version=3, token_type="access")

    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == str(user_id)
    assert payload["pv"] == 3
    assert payload["typ"] == "access"


def test_token_type_must_match():
    """refresh 令牌不能当 access 用。"""
    token = create_token(user_id=uuid.uuid4(), token_version=0, token_type="refresh")

    with pytest.raises(TokenInvalidError):
        decode_token(token, expected_type="access")


def test_expired_token_raises_expired_error():
    """过期必须抛 TokenExpiredError（前端只对它触发刷新，对应 AUTH_002）。"""
    payload = {
        "sub": str(uuid.uuid4()),
        "pv": 0,
        "typ": "access",
        "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(TokenExpiredError):
        decode_token(token, expected_type="access")


def test_tampered_token_is_invalid():
    token = create_token(user_id=uuid.uuid4(), token_version=0, token_type="access")
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")

    with pytest.raises(TokenInvalidError):
        decode_token(tampered, expected_type="access")


def test_token_signed_with_other_key_is_invalid():
    """用别的密钥签的令牌必须被拒（长度 ≥32 字节，避免 PyJWT 的弱密钥告警）。"""
    payload = {"sub": str(uuid.uuid4()), "pv": 0, "typ": "access", "exp": 9999999999}
    token = jwt.encode(
        payload,
        "another-secret-key-at-least-32-bytes!",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenInvalidError):
        decode_token(token, expected_type="access")
