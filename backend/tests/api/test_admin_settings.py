"""管理端：系统配置与操作审计（契约：docs/api.md §16.5 / §16.6）。

覆盖点：非管理员 403、只读键拒写、类型与范围校验、写后立即生效（缓存失效）、
审计与业务同事务、审计只读且可筛选。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog
from app.services import audit_service, setting_service

SETTINGS_URL = "/api/v1/admin/settings"
AUDIT_URL = "/api/v1/admin/audit-logs"


# ------------------------------------------------------------------ 权限


async def test_normal_user_cannot_touch_admin_endpoints(db_client, auth_headers):
    read = await db_client.get(SETTINGS_URL, headers=auth_headers)
    write = await db_client.patch(
        SETTINGS_URL, json={"items": [{"key": "ai.enabled", "value": False}]}, headers=auth_headers
    )
    audit = await db_client.get(AUDIT_URL, headers=auth_headers)

    # 契约：管理端角色不足是 403（用户端越权才是 404）
    for resp in (read, write, audit):
        assert resp.status_code == 403
        assert resp.json()["code"] == "AUTH_004"


async def test_anonymous_cannot_touch_admin_endpoints(db_client):
    resp = await db_client.get(SETTINGS_URL)

    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_001"


# ------------------------------------------------------------------ 13.5 配置读取


async def test_list_settings_shows_seeded_keys(db_client, admin_headers):
    resp = await db_client.get(SETTINGS_URL, headers=admin_headers)

    assert resp.status_code == 200, resp.text
    items = {item["key"]: item for item in resp.json()["items"]}
    assert set(items) == {
        "ai.daily_quota",
        "ai.enabled",
        "ai.model_name",
        "register.allow",
        "upload.max_mb",
    }
    assert items["ai.daily_quota"]["value"] == 100
    assert items["ai.daily_quota"]["value_type"] == "int"
    assert items["ai.daily_quota"]["editable"] is True
    assert items["ai.daily_quota"]["description"]
    # 模型名只读展示，且取的是**当前部署配置**（.env 的 LLM_MODEL）
    assert items["ai.model_name"]["editable"] is False
    assert items["ai.model_name"]["value"]


# ------------------------------------------------------------------ 13.5 配置写入


async def test_update_setting_takes_effect_immediately_and_logs_audit(
    db_client, admin_headers, db_session: AsyncSession
):
    resp = await db_client.patch(
        SETTINGS_URL,
        json={
            "items": [
                {"key": "ai.daily_quota", "value": 200},
                {"key": "ai.enabled", "value": False},
            ]
        },
        headers=admin_headers,
    )

    assert resp.status_code == 200, resp.text
    items = {item["key"]: item for item in resp.json()["items"]}
    assert items["ai.daily_quota"]["value"] == 200
    assert items["ai.enabled"]["value"] is False
    assert items["ai.daily_quota"]["updated_by_username"] == "test_admin"

    # 缓存立即失效：同一个进程里再读就是新值
    db_session.expire_all()
    assert await setting_service.get_int(db_session, "ai.daily_quota") == 200
    assert await setting_service.is_enabled(db_session, "ai.enabled") is False

    # 审计与业务同事务写入，detail 里带前后快照
    logs = await db_client.get(AUDIT_URL, headers=admin_headers)
    entry = logs.json()["items"][0]
    assert entry["action"] == "setting.update"
    assert entry["target_type"] == "setting"
    assert entry["admin"]["username"] == "test_admin"
    changes = {change["key"]: change for change in entry["detail"]["changes"]}
    assert changes["ai.daily_quota"]["from"] == 100
    assert changes["ai.daily_quota"]["to"] == 200
    assert changes["ai.enabled"]["to"] is False


async def test_update_rejects_readonly_key(db_client, admin_headers, db_session: AsyncSession):
    # 审计表是持久化的（本地库里有真实操作记录），所以断言「没有新增」而不是「总数为 0」
    before = await db_session.scalar(
        select(func.count())
        .select_from(AdminAuditLog)
        .where(AdminAuditLog.action == audit_service.ACTION_SETTING_UPDATE)
    )

    resp = await db_client.patch(
        SETTINGS_URL,
        json={"items": [{"key": "ai.model_name", "value": "gpt-9"}]},
        headers=admin_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "SYS_400"
    assert "只读" in resp.json()["message"]

    after = await db_session.scalar(
        select(func.count())
        .select_from(AdminAuditLog)
        .where(AdminAuditLog.action == audit_service.ACTION_SETTING_UPDATE)
    )
    assert int(after or 0) == int(before or 0)


async def test_update_rejects_unknown_key(db_client, admin_headers):
    resp = await db_client.patch(
        SETTINGS_URL,
        json={"items": [{"key": "not.exists", "value": 1}]},
        headers=admin_headers,
    )

    assert resp.status_code == 400
    assert "未知配置项" in resp.json()["message"]


async def test_update_validates_type_and_range(db_client, admin_headers):
    too_big = await db_client.patch(
        SETTINGS_URL,
        json={"items": [{"key": "ai.daily_quota", "value": 99999}]},
        headers=admin_headers,
    )
    not_int = await db_client.patch(
        SETTINGS_URL,
        json={"items": [{"key": "ai.daily_quota", "value": "abc"}]},
        headers=admin_headers,
    )
    not_bool = await db_client.patch(
        SETTINGS_URL,
        json={"items": [{"key": "ai.enabled", "value": "yes"}]},
        headers=admin_headers,
    )

    assert too_big.status_code == 400
    assert "1..10000" in too_big.json()["message"]
    assert not_int.status_code == 400
    assert not_bool.status_code == 400
    assert "布尔" in not_bool.json()["message"]


async def test_update_rejects_empty_items(db_client, admin_headers):
    resp = await db_client.patch(SETTINGS_URL, json={"items": []}, headers=admin_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


# ------------------------------------------------------------------ 13.5 审计


async def test_audit_logs_are_append_only_and_filterable(
    db_client, admin_headers, admin_user, db_session: AsyncSession
):
    await db_client.patch(
        SETTINGS_URL,
        json={"items": [{"key": "upload.max_mb", "value": 30}]},
        headers=admin_headers,
    )
    await db_client.patch(
        SETTINGS_URL,
        json={"items": [{"key": "register.allow", "value": False}]},
        headers=admin_headers,
    )

    # 按「本次用例的管理员」过滤：审计表是持久化的，开发库里会有别的记录
    query = f"admin_id={admin_user.id}"
    all_logs = await db_client.get(f"{AUDIT_URL}?{query}", headers=admin_headers)
    assert all_logs.json()["total"] == 2
    # 最近的排前面
    assert all_logs.json()["items"][0]["detail"]["changes"][0]["key"] == "register.allow"

    by_target = await db_client.get(
        f"{AUDIT_URL}?{query}&target_type=setting", headers=admin_headers
    )
    assert by_target.json()["total"] == 2

    by_other = await db_client.get(
        f"{AUDIT_URL}?{query}&target_type=user", headers=admin_headers
    )
    assert by_other.json()["total"] == 0

    by_action = await db_client.get(
        f"{AUDIT_URL}?{query}&action=user.disable", headers=admin_headers
    )
    assert by_action.json()["total"] == 0

    # 没有删除接口：DELETE 落到 405（只增不改不删）
    deleted = await db_client.delete(AUDIT_URL, headers=admin_headers)
    assert deleted.status_code == 405


async def test_audit_logs_validate_pagination(db_client, admin_headers):
    resp = await db_client.get(f"{AUDIT_URL}?page=0", headers=admin_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"
