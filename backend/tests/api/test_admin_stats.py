"""管理端：仪表盘统计与 AI 用量（契约：docs/api.md §16.1 / §16.4）。

写法要点：概览里的全站计数会被本地开发库里的真实数据影响，
所以断言一律用「先取一次 → 造数据 → 再取一次」的**增量**比较，
不写死总数。
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiUsage, Material, Quiz
from app.services import admin_stats_service
from app.utils.time import today_local

OVERVIEW_URL = "/api/v1/admin/stats/overview"
DAILY_URL = "/api/v1/admin/stats/daily"
AI_STATS_URL = "/api/v1/admin/stats/ai"
AI_USAGE_URL = "/api/v1/admin/ai-usage"


def seed_material(user_id: uuid.UUID) -> Material:
    return Material(
        user_id=user_id,
        title="管理端测试资料",
        file_name="admin.pdf",
        file_ext=".pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        file_path="materials/admin.pdf",
        file_hash="a" * 64,
        parse_status="success",
        extracted_text="极限的定义。" * 10,
        char_count=70,
    )


def seed_quiz(user_id: uuid.UUID) -> Quiz:
    return Quiz(
        user_id=user_id,
        title="管理端测试题",
        question_count=1,
        types=["single"],
        difficulty="medium",
        question_data=[
            {
                "no": 1,
                "type": "single",
                "stem": "题干",
                "options": ["A", "B", "C", "D"],
                "answer": ["A"],
                "difficulty": "medium",
                "knowledge": "极限",
            }
        ],
        model="stub",
    )


def seed_usage(user_id: uuid.UUID, *, scene: str = "summary", ok: bool = True) -> AiUsage:
    return AiUsage(
        user_id=user_id,
        scene=scene,
        model="stub-model",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        steps=2,
        latency_ms=1200,
        ok=ok,
        error_code=None if ok else "AI_002",
    )


# ------------------------------------------------------------------ 13.1 概览


async def test_overview_counts_deltas(
    db_client, admin_headers, auth_headers, test_user, db_session: AsyncSession
):
    before = (await db_client.get(OVERVIEW_URL, headers=admin_headers)).json()

    # 造内容：资料与测试题直接写库，笔记 / 计划走接口（字段简单）
    db_session.add(seed_material(test_user.id))
    db_session.add(seed_quiz(test_user.id))
    db_session.add(seed_usage(test_user.id, scene="summary", ok=True))
    db_session.add(seed_usage(test_user.id, scene="qa", ok=False))
    await db_session.commit()

    note = await db_client.post(
        "/api/v1/notes",
        json={"title": "管理端测试笔记", "content": "内容"},
        headers=auth_headers,
    )
    assert note.status_code == 201, note.text
    plan = await db_client.post(
        "/api/v1/plans",
        json={
            "title": "管理端测试计划",
            "start_date": today_local().isoformat(),
            "end_date": (today_local() + timedelta(days=2)).isoformat(),
            "daily_minutes": 30,
        },
        headers=auth_headers,
    )
    assert plan.status_code == 201, plan.text

    resp = await db_client.get(f"{OVERVIEW_URL}?days=30", headers=admin_headers)
    after = resp.json()

    assert resp.status_code == 200
    assert after["range"]["days"] == 30
    assert after["users"]["total"] >= before["users"]["total"]
    assert after["users"]["admins"] >= 1

    for key in ("materials", "notes", "plans", "quizzes"):
        assert after["content"][key] == before["content"][key] + 1, key

    assert after["ai"]["calls"] == before["ai"]["calls"] + 2
    assert after["ai"]["total_tokens"] == before["ai"]["total_tokens"] + 300
    assert 0.0 <= after["ai"]["success_rate"] <= 1.0


async def test_overview_validates_days(db_client, admin_headers):
    resp = await db_client.get(f"{OVERVIEW_URL}?days=0", headers=admin_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


# ------------------------------------------------------------------ 13.1 每日趋势


async def test_daily_fills_every_day(db_client, admin_headers, auth_headers):
    today = today_local()
    created = await db_client.post(
        "/api/v1/study-records",
        json={
            "type": "reading",
            "started_at": f"{today.isoformat()}T09:00:00+08:00",
            "duration_minutes": 40,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    resp = await db_client.get(
        DAILY_URL,
        params={"from": (today - timedelta(days=4)).isoformat(), "to": today.isoformat()},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 5  # 一天不缺
    assert items[-1]["date"] == today.isoformat()
    # 今天至少有刚才那条 40 分钟（开发库可能还有别的数据，所以用 >=）
    assert items[-1]["study_minutes"] >= 40
    assert items[0]["study_minutes"] >= 0


async def test_daily_supports_alias_from_to(db_client, admin_headers):
    today = today_local()
    resp = await db_client.get(
        f"{DAILY_URL}?from={(today - timedelta(days=1)).isoformat()}&to={today.isoformat()}",
        headers=admin_headers,
    )

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


# ------------------------------------------------------------------ 13.4 AI 分布


async def test_ai_stats_by_scene_users_and_daily(
    db_client, admin_headers, test_user, db_session: AsyncSession
):
    db_session.add(seed_usage(test_user.id, scene="summary", ok=True))
    db_session.add(seed_usage(test_user.id, scene="summary", ok=True))
    db_session.add(seed_usage(test_user.id, scene="quiz", ok=False))
    await db_session.commit()

    resp = await db_client.get(f"{AI_STATS_URL}?days=30", headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()

    by_scene = {row["scene"]: row for row in data["by_scene"]}
    assert by_scene["summary"]["calls"] >= 2
    assert 0.0 <= by_scene["summary"]["success_rate"] <= 1.0
    assert by_scene["summary"]["avg_latency_ms"] >= 0

    usernames = [row["username"] for row in data["top_users"]]
    assert "test_user" in usernames

    assert len(data["daily"]) == 30  # 补零
    assert data["daily"][-1]["date"] == today_local().isoformat()


# ------------------------------------------------------------------ 13.4 调用明细


async def test_ai_usage_list_filters_and_pagination(
    db_client, admin_headers, test_user, db_session: AsyncSession
):
    db_session.add(seed_usage(test_user.id, scene="summary", ok=True))
    db_session.add(seed_usage(test_user.id, scene="quiz", ok=False))
    await db_session.commit()

    all_rows = await db_client.get(AI_USAGE_URL, headers=admin_headers)
    assert all_rows.status_code == 200
    assert all_rows.json()["total"] >= 2
    assert all_rows.json()["items"][0]["user"]["username"]

    by_scene = await db_client.get(f"{AI_USAGE_URL}?scene=quiz", headers=admin_headers)
    assert by_scene.json()["total"] >= 1
    assert all(item["scene"] == "quiz" for item in by_scene.json()["items"])

    failed = await db_client.get(f"{AI_USAGE_URL}?ok=false", headers=admin_headers)
    assert failed.json()["total"] >= 1
    assert all(item["ok"] is False for item in failed.json()["items"])
    assert failed.json()["items"][0]["error_code"] == "AI_002"

    by_user = await db_client.get(f"{AI_USAGE_URL}?user_id={test_user.id}", headers=admin_headers)
    assert by_user.json()["total"] >= 2

    paged = await db_client.get(f"{AI_USAGE_URL}?page=1&size=1", headers=admin_headers)
    assert len(paged.json()["items"]) == 1
    assert paged.json()["size"] == 1


async def test_ai_usage_service_returns_joined_username(db_session, test_user):
    """直接测 service：确认 join 出了用户名（不依赖 HTTP 层）。"""
    db_session.add(seed_usage(test_user.id))
    await db_session.commit()

    items, total = await admin_stats_service.list_ai_usage(
        db_session, offset=0, limit=5, user_id=test_user.id
    )

    assert total >= 1
    assert items[0]["user"]["username"] == test_user.username
    assert isinstance(items[0]["created_at"], datetime)
