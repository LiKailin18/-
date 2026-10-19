"""用户接口测试（契约：docs/api.md §4）—— 功能 2。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_token
from app.models import AppUser
from app.schemas.user import UserCreate
from app.services import user_service
from tests.conftest import TEST_PASSWORD, login

ME_URL = "/api/v1/users/me"
PASSWORD_URL = "/api/v1/users/me/password"

USER_FIELDS = {
    "id",
    "username",
    "email",
    "nickname",
    "avatar_url",
    "learning_goal",
    "daily_target_minutes",
    "role",
    "created_at",
}


# ------------------------------------------------------------------ 鉴权


async def test_me_without_token_is_unauthorized(db_client):
    resp = await db_client.get(ME_URL)

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_001"
    # 统一错误体：{code, message, detail}
    assert set(body) == {"code", "message", "detail"}


async def test_me_with_garbage_token_is_invalid(db_client):
    resp = await db_client.get(ME_URL, headers={"Authorization": "Bearer not-a-jwt"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_003"


async def test_me_with_stale_token_version_is_rejected(
    db_client, db_session: AsyncSession, test_user: AppUser
):
    """改密码 / 改角色后，旧令牌的 pv 与库里不一致 → 必须失效。"""
    stale = create_token(
        user_id=test_user.id, token_version=test_user.token_version, token_type="access"
    )
    test_user.token_version += 1
    await db_session.commit()

    resp = await db_client.get(ME_URL, headers={"Authorization": f"Bearer {stale}"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_003"


async def test_me_with_disabled_account_is_forbidden(
    db_client, db_session: AsyncSession, test_user: AppUser, auth_headers
):
    test_user.is_active = False
    test_user.disabled_reason = "违规"
    await db_session.commit()

    resp = await db_client.get(ME_URL, headers=auth_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "USER_003"


# ------------------------------------------------------------------ 查询与修改


async def test_me_returns_contract_fields(db_client, test_user: AppUser, auth_headers):
    resp = await db_client.get(ME_URL, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == USER_FIELDS
    assert body["username"] == test_user.username
    assert body["nickname"] == "测试用户"
    assert "password_hash" not in resp.text


async def test_patch_me_updates_only_given_fields(db_client, test_user, auth_headers):
    resp = await db_client.patch(
        ME_URL,
        json={"nickname": "改名了", "learning_goal": "通过期末考试", "daily_target_minutes": 90},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nickname"] == "改名了"
    assert body["learning_goal"] == "通过期末考试"
    assert body["daily_target_minutes"] == 90
    # 未提交的字段保持原值
    assert body["email"] == test_user.email


async def test_patch_me_can_clear_optional_field(db_client, test_user, auth_headers):
    """显式传 null 表示清空，与「未提交」不同。"""
    resp = await db_client.patch(ME_URL, json={"nickname": None}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["nickname"] is None


async def test_patch_me_rejects_other_users_email(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    other = await user_service.create_user(
        db_session,
        UserCreate(username="other_user", email="other@example.com", password=TEST_PASSWORD),
    )

    resp = await db_client.patch(ME_URL, json={"email": other.email}, headers=auth_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "USER_002"


async def test_patch_me_validates_daily_target_range(db_client, auth_headers):
    resp = await db_client.patch(ME_URL, json={"daily_target_minutes": 0}, headers=auth_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


async def test_two_users_only_see_their_own_profile(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    """数据隔离：A 的令牌只能拿到 A 的资料（不是查出来再判断，而是各自 /me）。"""
    await user_service.create_user(
        db_session,
        UserCreate(
            username="isolated_user",
            email="isolated@example.com",
            password=TEST_PASSWORD,
            nickname="另一个人",
        ),
    )
    other_headers = await login(db_client, "isolated_user", TEST_PASSWORD)

    first = await db_client.get(ME_URL, headers=auth_headers)
    second = await db_client.get(ME_URL, headers=other_headers)

    assert first.json()["username"] == test_user.username
    assert second.json()["username"] == "isolated_user"
    assert first.json()["id"] != second.json()["id"]


# ------------------------------------------------------------------ 改密码


async def test_change_password_rejects_wrong_old_password(db_client, auth_headers):
    resp = await db_client.post(
        PASSWORD_URL,
        json={"old_password": "WrongPass1", "new_password": "NewPass123"},
        headers=auth_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "USER_004"


async def test_change_password_revokes_existing_tokens(
    db_client, test_user: AppUser, auth_headers
):
    """改密码 → token_version +1 → 旧 access 令牌立即失效（契约 §4）。"""
    resp = await db_client.post(
        PASSWORD_URL,
        json={"old_password": TEST_PASSWORD, "new_password": "NewPass123"},
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text

    # 旧令牌不可用
    stale = await db_client.get(ME_URL, headers=auth_headers)
    assert stale.status_code == 401
    assert stale.json()["code"] == "AUTH_003"

    # 新密码可以登录
    new_headers = await login(db_client, test_user.username, "NewPass123")
    ok = await db_client.get(ME_URL, headers=new_headers)
    assert ok.status_code == 200
