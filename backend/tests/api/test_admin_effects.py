"""系统配置的**生效点**（契约：docs/api.md §16.5）。

配置不是摆设：`ai.enabled` / `register.allow` / `ai.daily_quota` / `upload.max_mb`
都在真实链路上被读取。这里验证「改完立即生效、不用重启」。
"""

import uuid

ADMIN_SETTINGS = "/api/v1/admin/settings"


async def _patch_settings(db_client, admin_headers, items: list[dict]) -> None:
    resp = await db_client.patch(ADMIN_SETTINGS, json={"items": items}, headers=admin_headers)
    assert resp.status_code == 200, resp.text


async def test_ai_disabled_blocks_whole_ai_group(db_client, admin_headers, auth_headers):
    await _patch_settings(db_client, admin_headers, [{"key": "ai.enabled", "value": False}])

    # 生成类接口 503
    summary = await db_client.post(
        "/api/v1/ai/summaries",
        json={"material_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert summary.status_code == 503
    assert summary.json()["code"] == "SYS_503"
    assert "暂停" in summary.json()["message"]

    # 整组 /ai/* 都 503（前端据此置灰入口并提示）
    usage = await db_client.get("/api/v1/ai/usage", headers=auth_headers)
    assert usage.status_code == 503

    # 但答卷判分不属于这一组：它不调用模型，不该被关掉
    quizzes = await db_client.get("/api/v1/quizzes", headers=auth_headers)
    assert quizzes.status_code == 200

    # 重新打开后立刻恢复（缓存写后即清）
    await _patch_settings(db_client, admin_headers, [{"key": "ai.enabled", "value": True}])
    reopened = await db_client.post(
        "/api/v1/ai/summaries",
        json={"material_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    # 闸门已经放行，所以这次是「资料不存在」而不是 503
    assert reopened.status_code != 503


async def test_register_disabled_returns_503(db_client, admin_headers):
    await _patch_settings(db_client, admin_headers, [{"key": "register.allow", "value": False}])

    payload = {
        "username": "closed_register",
        "email": "closed@example.com",
        "password": "Test1234!",
    }
    blocked = await db_client.post("/api/v1/auth/register", json=payload)
    assert blocked.status_code == 503
    assert blocked.json()["code"] == "SYS_503"

    # 重新开放后可以注册（证明配置立刻生效，不是 60 秒后才生效）
    await _patch_settings(db_client, admin_headers, [{"key": "register.allow", "value": True}])
    ok = await db_client.post("/api/v1/auth/register", json=payload)
    assert ok.status_code == 201, ok.text


async def test_daily_quota_is_read_from_settings(db_client, admin_headers, auth_headers):
    await _patch_settings(db_client, admin_headers, [{"key": "ai.daily_quota", "value": 7}])

    usage = await db_client.get("/api/v1/ai/usage", headers=auth_headers)
    assert usage.status_code == 200
    assert usage.json()["daily_quota"] == 7
