"""健康检查接口测试（契约：docs/api.md §1.6）。

覆盖点：
1. 数据库正常 → 200 / status=ok
2. 数据库不可用 → 503 / status=degraded（容器编排依赖这个状态码）
3. 响应体字段与契约完全一致，且不泄露原始异常
4. Swagger（openapi.json）可生成 —— 它是交付物
"""

import pytest

from app.api import health as health_module

CONTRACT_FIELDS = {"status", "db", "version"}


async def test_health_ok_when_db_available(client, monkeypatch):
    async def fake_check_db() -> bool:
        return True

    monkeypatch.setattr(health_module, "check_db", fake_check_db)

    resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert set(body) == CONTRACT_FIELDS


async def test_health_degraded_when_db_down(client, monkeypatch):
    async def fake_check_db() -> bool:
        return False

    monkeypatch.setattr(health_module, "check_db", fake_check_db)

    resp = await client.get("/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "down"
    # 契约要求：不向调用方暴露原始异常与堆栈
    assert "Traceback" not in resp.text
    assert "asyncpg" not in resp.text


async def test_openapi_available(client):
    resp = await client.get("/openapi.json")

    assert resp.status_code == 200
    spec = resp.json()
    assert "/health" in spec["paths"]
    assert spec["info"]["title"] == "智能学习系统 API"


@pytest.mark.integration
async def test_health_with_real_database(client):
    """需要真实 PostgreSQL；没有数据库时跳过而不是失败。"""
    resp = await client.get("/health")

    if resp.status_code == 503:
        pytest.skip("本机没有可用的 PostgreSQL，跳过真实数据库连通测试")

    assert resp.json()["db"] == "ok"
