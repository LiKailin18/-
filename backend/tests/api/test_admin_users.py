"""管理端用户管理（契约：docs/api.md §16.2）。

重点验证四条规则：
1. counts 用相关子查询一次取回（用 SQL 语句计数证明没有 N+1）
2. 禁用 / 改角色会让旧令牌立即失效（token_version + 1）
3. 禁用必须填原因；启用会清空原因
4. 管理员不能禁用 / 降级 / 重置自己（400 ADMIN_001）
"""

import uuid

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import engine
from app.models import AppSetting, AppUser, Material, Note
from app.services import setting_service

USERS_URL = "/api/v1/admin/users"


async def test_list_users_returns_counts_in_one_aggregate_query(
    db_client, admin_headers, test_user, db_session: AsyncSession
):
    db_session.add(
        Material(
            user_id=test_user.id,
            title="用户的资料",
            file_name="u.pdf",
            file_ext=".pdf",
            mime_type="application/pdf",
            size_bytes=10,
            file_path="materials/u.pdf",
            file_hash="b" * 64,
        )
    )
    db_session.add(Note(user_id=test_user.id, title="用户的笔记", content="内容"))
    await db_session.commit()

    statements: list[str] = []

    def _record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        resp = await db_client.get(
            f"{USERS_URL}?keyword=test_user", headers=admin_headers
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    target = next(item for item in items if item["username"] == "test_user")
    assert target["counts"]["materials"] == 1
    assert target["counts"]["notes"] == 1
    assert target["counts"]["ai_calls_30d"] >= 0
    assert target["counts"]["study_minutes_30d"] >= 0

    # 认证 1 条 + 总数 1 条 + 列表 1 条 —— 如果逐行查 counts 会随用户数线性增长
    assert len(statements) <= 6, "\n---\n".join(statements)


async def test_user_detail_includes_quiz_accuracy(db_client, admin_headers, test_user):
    resp = await db_client.get(f"{USERS_URL}/{test_user.id}", headers=admin_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["username"] == test_user.username
    assert body["quiz_accuracy_30d"] == 0.0
    assert body["ai_tokens_30d"] >= 0


async def test_disable_user_requires_reason(db_client, admin_headers, test_user):
    resp = await db_client.patch(
        f"{USERS_URL}/{test_user.id}",
        json={"is_active": False},
        headers=admin_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "SYS_400"
    assert "原因" in resp.json()["message"]


async def test_disable_invalidates_old_tokens(
    db_client, admin_headers, auth_headers, test_user
):
    # 先确认旧令牌可用
    me = await db_client.get("/api/v1/users/me", headers=auth_headers)
    assert me.status_code == 200

    resp = await db_client.patch(
        f"{USERS_URL}/{test_user.id}",
        json={"is_active": False, "disabled_reason": "上传违规内容"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False
    assert resp.json()["disabled_reason"] == "上传违规内容"

    # token_version + 1 → 旧 access token 立即失效（401 AUTH_003）
    blocked = await db_client.get("/api/v1/users/me", headers=auth_headers)
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "AUTH_003"

    # 重新启用后原因被清空
    enabled = await db_client.patch(
        f"{USERS_URL}/{test_user.id}",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert enabled.status_code == 200
    assert enabled.json()["is_active"] is True
    assert enabled.json()["disabled_reason"] is None


async def test_role_change_takes_effect_and_invalidates_tokens(
    db_client, admin_headers, auth_headers, test_user
):
    promoted = await db_client.patch(
        f"{USERS_URL}/{test_user.id}",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "admin"

    # 旧令牌作废
    stale = await db_client.get("/api/v1/users/me", headers=auth_headers)
    assert stale.status_code == 401

    # 重新登录后确实拿到了管理端权限（角色读库，不信令牌声明）
    relogin = await db_client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Test1234!"},
    )
    assert relogin.status_code == 200
    new_headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    admin_ok = await db_client.get(USERS_URL, headers=new_headers)
    assert admin_ok.status_code == 200


async def test_admin_cannot_operate_on_self(db_client, admin_headers, admin_user):
    cases = [
        ("PATCH", f"{USERS_URL}/{admin_user.id}", {"is_active": False, "disabled_reason": "x"}),
        ("PATCH", f"{USERS_URL}/{admin_user.id}", {"role": "user"}),
        ("POST", f"{USERS_URL}/{admin_user.id}/reset-password", None),
        ("POST", f"{USERS_URL}/{admin_user.id}/revoke-tokens", None),
    ]
    for method, url, body in cases:
        resp = await db_client.request(method, url, json=body, headers=admin_headers)
        assert resp.status_code == 400, f"{method} {url} -> {resp.status_code}"
        assert resp.json()["code"] == "ADMIN_001"


async def test_reset_password_returns_one_time_password(
    db_client, admin_headers, test_user
):
    resp = await db_client.post(
        f"{USERS_URL}/{test_user.id}/reset-password", headers=admin_headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    password = body["temporary_password"]
    assert len(password) == 12
    assert body["note"]

    # 旧密码失效、临时密码可用
    old = await db_client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Test1234!"},
    )
    assert old.status_code == 401

    new = await db_client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": password},
    )
    assert new.status_code == 200


async def test_revoke_tokens_invalidates_sessions(
    db_client, admin_headers, auth_headers, test_user
):
    resp = await db_client.post(
        f"{USERS_URL}/{test_user.id}/revoke-tokens", headers=admin_headers
    )

    assert resp.status_code == 204
    blocked = await db_client.get("/api/v1/users/me", headers=auth_headers)
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "AUTH_003"


async def test_unknown_user_returns_404(db_client, admin_headers):
    missing = uuid.uuid4()

    detail = await db_client.get(f"{USERS_URL}/{missing}", headers=admin_headers)
    patch = await db_client.patch(
        f"{USERS_URL}/{missing}", json={"is_active": True}, headers=admin_headers
    )

    assert detail.status_code == 404
    assert detail.json()["code"] == "SYS_404"
    assert patch.status_code == 404


async def test_user_changes_are_audited(db_client, admin_headers, test_user):
    await db_client.patch(
        f"{USERS_URL}/{test_user.id}",
        json={"is_active": False, "disabled_reason": "测试审计"},
        headers=admin_headers,
    )
    await db_client.patch(
        f"{USERS_URL}/{test_user.id}", json={"role": "admin"}, headers=admin_headers
    )

    logs = await db_client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    actions = [item["action"] for item in logs.json()["items"]]

    assert "user.disable" in actions
    assert "user.role_change" in actions
    disable_log = next(
        item for item in logs.json()["items"] if item["action"] == "user.disable"
    )
    assert disable_log["target_id"] == str(test_user.id)
    assert disable_log["detail"]["to"]["disabled_reason"] == "测试审计"


async def test_disabled_user_cannot_login(db_client, admin_headers, test_user):
    await db_client.patch(
        f"{USERS_URL}/{test_user.id}",
        json={"is_active": False, "disabled_reason": "违规"},
        headers=admin_headers,
    )

    resp = await db_client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Test1234!"},
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "USER_003"
    assert "违规" in resp.json()["message"]


async def test_setting_effect_not_polluted_by_other_tests(db_session, test_user):
    """防止「配置缓存串场」的回归：默认配置是 100。"""
    row = await db_session.get(AppSetting, "ai.daily_quota")
    assert row is not None
    setting_service._cache.clear()
    assert await setting_service.get_int(db_session, "ai.daily_quota") == int(row.value)

    admin = await db_session.get(AppUser, test_user.id)
    assert admin is not None
