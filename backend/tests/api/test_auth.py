"""认证接口测试（契约：docs/api.md §3）—— 功能 1。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AppUser
from tests.conftest import TEST_PASSWORD, login

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"


def _register_body(**overrides) -> dict:
    body = {
        "username": "new_user",
        "email": "new_user@example.com",
        "password": "Test1234!",
        "nickname": "新用户",
    }
    body.update(overrides)
    return body


# ------------------------------------------------------------------ 注册


async def test_register_returns_created_user_without_password(db_client):
    resp = await db_client.post(REGISTER_URL, json=_register_body())

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["username"] == "new_user"
    assert body["email"] == "new_user@example.com"
    assert body["nickname"] == "新用户"
    assert body["role"] == "user"
    assert body["daily_target_minutes"] == 60
    # 契约：响应永不出现密码相关字段
    assert "password" not in body and "password_hash" not in body


async def test_register_duplicate_username_conflicts(db_client, test_user):
    resp = await db_client.post(REGISTER_URL, json=_register_body(username=test_user.username))

    assert resp.status_code == 409
    assert resp.json()["code"] == "USER_001"


async def test_register_duplicate_email_is_case_insensitive(db_client, test_user):
    """邮箱统一存小写，所以大小写不同也算重复。"""
    resp = await db_client.post(
        REGISTER_URL, json=_register_body(email=test_user.email.upper())
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "USER_002"


async def test_register_rejects_weak_password(db_client):
    resp = await db_client.post(REGISTER_URL, json=_register_body(password="onlyletters"))

    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "SYS_422"
    # detail 给到字段级错误，前端可直接定位表单项
    assert any(err["loc"][-1] == "password" for err in body["detail"])


async def test_register_rejects_bad_email(db_client):
    resp = await db_client.post(REGISTER_URL, json=_register_body(email="not-an-email"))

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


# ------------------------------------------------------------------ 登录


async def test_login_returns_token_and_sets_refresh_cookie(db_client, test_user):
    resp = await db_client.post(
        LOGIN_URL, data={"username": test_user.username, "password": TEST_PASSWORD}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60
    assert body["role"] == "user"
    assert body["access_token"]

    cookie = resp.headers["set-cookie"]
    assert settings.refresh_cookie_name in cookie
    assert "HttpOnly" in cookie
    assert f"Path={settings.refresh_cookie_path}" in cookie
    assert "SameSite=lax" in cookie.lower() or "samesite=lax" in cookie.lower()


async def test_login_wrong_password_returns_unspecified_message(db_client, test_user):
    resp = await db_client.post(
        LOGIN_URL, data={"username": test_user.username, "password": "WrongPass1"}
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_003"
    # 不区分「用户不存在」与「密码错误」
    assert body["message"] == "用户名或密码错误"


async def test_login_unknown_user_same_message(db_client):
    resp = await db_client.post(LOGIN_URL, data={"username": "ghost", "password": "Test1234!"})

    assert resp.status_code == 401
    assert resp.json()["message"] == "用户名或密码错误"


async def test_login_disabled_account_forbidden(
    db_client, db_session: AsyncSession, test_user: AppUser
):
    test_user.is_active = False
    test_user.disabled_reason = "上传违规内容"
    await db_session.commit()

    resp = await db_client.post(
        LOGIN_URL, data={"username": test_user.username, "password": TEST_PASSWORD}
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "USER_003"
    assert "上传违规内容" in body["message"]


async def test_login_response_contains_no_password_fields(db_client, test_user):
    """登录响应只有令牌，不应出现任何密码相关字段。"""
    resp = await db_client.post(
        LOGIN_URL, data={"username": test_user.username, "password": TEST_PASSWORD}
    )

    assert resp.status_code == 200
    assert "password" not in resp.text
    assert set(resp.json()) == {"access_token", "token_type", "expires_in", "role"}


# ------------------------------------------------------------------ 刷新


async def test_refresh_without_cookie_is_unauthorized(db_client):
    resp = await db_client.post(REFRESH_URL)

    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_001"


async def test_refresh_rotates_token(db_client, test_user):
    """登录后由 client 自动带上 refresh Cookie，刷新应发新 access 并轮换 Cookie。"""
    await login(db_client, test_user.username, TEST_PASSWORD)
    first_cookie = db_client.cookies.get(settings.refresh_cookie_name)

    resp = await db_client.post(REFRESH_URL)

    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    rotated = resp.headers.get("set-cookie", "")
    assert settings.refresh_cookie_name in rotated
    assert db_client.cookies.get(settings.refresh_cookie_name) != first_cookie


async def test_refresh_rejects_foreign_origin(db_client, test_user):
    """CSRF 防护：Cookie 凭证接口校验 Origin（契约 §1.5）。"""
    await login(db_client, test_user.username, TEST_PASSWORD)

    resp = await db_client.post(REFRESH_URL, headers={"Origin": "http://evil.example.com"})

    assert resp.status_code == 403
    assert resp.json()["code"] == "AUTH_005"


async def test_refresh_accepts_allowed_origin(db_client, test_user):
    await login(db_client, test_user.username, TEST_PASSWORD)

    resp = await db_client.post(
        REFRESH_URL, headers={"Origin": settings.cors_origin_list[0]}
    )

    assert resp.status_code == 200


async def test_refresh_rejects_access_token_used_as_refresh(db_client, test_user):
    """把 access 令牌塞进 refresh Cookie 必须被拒绝（typ 校验）。"""
    headers = await login(db_client, test_user.username, TEST_PASSWORD)
    access_token = headers["Authorization"].removeprefix("Bearer ")

    # 直接覆盖客户端 cookie jar（per-request cookies 已被 httpx 标记为废弃）
    db_client.cookies.set(
        settings.refresh_cookie_name,
        access_token,
        domain="test.local",
        path=settings.refresh_cookie_path,
    )

    resp = await db_client.post(REFRESH_URL, headers={"Origin": settings.cors_origin_list[0]})

    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_003"


# ------------------------------------------------------------------ 登出


async def test_logout_clears_cookie(db_client, test_user):
    await login(db_client, test_user.username, TEST_PASSWORD)

    resp = await db_client.post(LOGOUT_URL, headers={"Origin": settings.cors_origin_list[0]})

    assert resp.status_code == 204
    assert settings.refresh_cookie_name not in db_client.cookies


async def test_logout_is_idempotent_without_cookie(db_client):
    resp = await db_client.post(LOGOUT_URL)

    assert resp.status_code == 204
