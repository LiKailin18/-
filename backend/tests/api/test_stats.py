"""统计与个性化推荐接口测试（契约：docs/api.md §12）。

- §12.1 统计（功能 11）：概览、每日趋势（补零）、科目分布、薄弱知识点
- §12.2 推荐（功能 10 规则层）：优先级顺序、limit、只剩「习惯」的情况

数据尽量通过接口造（plan / task / record）；只有 quiz / quiz_attempt 直接写库
—— 那两张表只有 AI 场景才写，走接口要打桩，反而绕。
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models import Material, Quiz, QuizAttempt
from app.services import stats_service
from app.utils.time import today_local
from tests.conftest import TEST_PASSWORD, login

STATS_URL = "/api/v1/stats"
RECS_URL = "/api/v1/recommendations"
PLANS_URL = "/api/v1/plans"
TASKS_URL = "/api/v1/tasks"
RECORDS_URL = "/api/v1/study-records"


# ------------------------------------------------------------------ 造数据的小工具


async def make_plan(
    db_client,
    auth_headers,
    *,
    start: date,
    days: int = 3,
    subject: str | None = "高数",
    status: str | None = None,
    title: str = "统计测试计划",
) -> dict:
    body = {
        "title": title,
        "subject": subject,
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=days - 1)).isoformat(),
        "daily_minutes": 45,
    }
    if status:
        body["status"] = status
    resp = await db_client.post(PLANS_URL, json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def generate_tasks(db_client, auth_headers, plan_id: str) -> list[dict]:
    resp = await db_client.post(
        f"{PLANS_URL}/{plan_id}/generate-tasks", json={}, headers=auth_headers
    )
    assert resp.status_code in (200, 201), resp.text
    listing = await db_client.get(f"{TASKS_URL}?plan_id={plan_id}", headers=auth_headers)
    return listing.json()["items"]


async def complete_task(db_client, auth_headers, task_id: str, *, minutes: int = 50) -> None:
    resp = await db_client.post(
        f"{TASKS_URL}/{task_id}/complete",
        json={"duration_minutes": minutes, "content": "完成任务"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


async def add_record(
    db_client,
    auth_headers,
    *,
    minutes: int = 30,
    task_id: str | None = None,
    days_ago: int = 0,
) -> None:
    body = {
        "type": "reading",
        "started_at": (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(),
        "duration_minutes": minutes,
        "content": "统计用例",
    }
    if task_id:
        body["task_id"] = task_id
    resp = await db_client.post(RECORDS_URL, json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text


async def seed_quiz(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    *,
    knowledge: str,
    attempts: int,
    correct: int,
) -> None:
    """造一份「只有 1 道题」的测验 + 若干答卷，供薄弱知识点用例使用。"""
    quiz = Quiz(
        user_id=user_id,
        title=f"{knowledge} 测验",
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
                "knowledge": knowledge,
            }
        ],
        model="stub",
    )
    db_session.add(quiz)
    await db_session.flush()

    for index in range(attempts):
        is_correct = index < correct
        db_session.add(
            QuizAttempt(
                quiz_id=quiz.id,
                user_id=user_id,
                answers=[
                    {"no": 1, "answer": ["A" if is_correct else "B"], "is_correct": is_correct}
                ],
                score=100 if is_correct else 0,
                correct_count=1 if is_correct else 0,
                question_count=1,
            )
        )
    await db_session.commit()


async def seed_unparsed_material(db_session: AsyncSession, user_id: uuid.UUID) -> Material:
    material = Material(
        user_id=user_id,
        title="没解析成功的资料",
        file_name="broken.pdf",
        file_ext=".pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        file_path="materials/broken.pdf",
        file_hash="0" * 64,
        parse_status="failed",
        parse_error="解析超时",
    )
    db_session.add(material)
    await db_session.commit()
    await db_session.refresh(material)
    return material


# ------------------------------------------------------------------ §12.1 概览


async def test_overview_of_empty_account_is_all_zeros(db_client, auth_headers):
    resp = await db_client.get(f"{STATS_URL}/overview", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period"]["days"] == 7
    assert body["period"]["from"] < body["period"]["to"]
    assert body["total_minutes"] == 0
    assert body["active_days"] == 0
    assert body["streak_days"] == 0
    # 契约：无数据时是 0.0，不是 null，也不能除零
    assert body["task_completion_rate"] == 0.0
    assert body["quiz_accuracy"] == 0.0
    assert body["materials"] == 0
    assert body["ai_calls"] == 0


async def test_overview_aggregates_minutes_tasks_and_accuracy(db_client, auth_headers):
    today = today_local()
    plan = await make_plan(db_client, auth_headers, start=today - timedelta(days=2))
    tasks = await generate_tasks(db_client, auth_headers, plan["id"])

    # 完成一个任务会自动写一条 50 分钟的学习记录；再手动补一条 25 分钟（不挂任务）
    await complete_task(db_client, auth_headers, tasks[0]["id"], minutes=50)
    await add_record(db_client, auth_headers, minutes=25)

    body = (await db_client.get(f"{STATS_URL}/overview", headers=auth_headers)).json()

    assert body["total_minutes"] == 75
    assert body["active_days"] == 1
    assert body["streak_days"] == 1
    assert body["task_total"] == 3
    assert body["task_done"] == 1
    assert body["task_completion_rate"] == round(1 / 3, 4)
    assert body["daily_avg_minutes"] == round(75 / 7, 1)


async def test_overview_skipped_task_not_counted_in_denominator(db_client, auth_headers):
    today = today_local()
    plan = await make_plan(db_client, auth_headers, start=today, days=2)
    tasks = await generate_tasks(db_client, auth_headers, plan["id"])

    await db_client.patch(
        f"{TASKS_URL}/{tasks[0]['id']}", json={"status": "skipped"}, headers=auth_headers
    )
    await complete_task(db_client, auth_headers, tasks[1]["id"], minutes=30)

    body = (await db_client.get(f"{STATS_URL}/overview", headers=auth_headers)).json()

    assert body["task_total"] == 1  # skipped 不进分母
    assert body["task_done"] == 1
    assert body["task_completion_rate"] == 1.0


async def test_overview_window_ignores_older_records(db_client, auth_headers):
    await add_record(db_client, auth_headers, minutes=60, days_ago=0)
    await add_record(db_client, auth_headers, minutes=90, days_ago=20)

    body = (await db_client.get(f"{STATS_URL}/overview?days=7", headers=auth_headers)).json()

    assert body["total_minutes"] == 60


# ------------------------------------------------------------------ §12.1 每日趋势


async def test_daily_fills_missing_days_with_zero(db_client, auth_headers):
    today = today_local()
    await add_record(db_client, auth_headers, minutes=30, days_ago=0)
    await add_record(db_client, auth_headers, minutes=45, days_ago=3)

    resp = await db_client.get(
        f"{STATS_URL}/daily",
        params={"date_from": (today - timedelta(days=4)).isoformat(), "date_to": today.isoformat()},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 5  # 一天不缺
    by_date = {item["date"]: item for item in items}
    assert by_date[(today - timedelta(days=3)).isoformat()]["minutes"] == 45
    assert by_date[today.isoformat()]["minutes"] == 30
    # 没有记录的日期补零，而不是缺行
    assert by_date[(today - timedelta(days=1)).isoformat()]["minutes"] == 0
    assert by_date[(today - timedelta(days=1)).isoformat()]["task_total"] == 0
    assert by_date[(today - timedelta(days=1)).isoformat()]["quiz_accuracy"] == 0.0


async def test_daily_defaults_to_last_30_days(db_client, auth_headers):
    items = (await db_client.get(f"{STATS_URL}/daily", headers=auth_headers)).json()["items"]

    assert len(items) == 30
    assert items[-1]["date"] == today_local().isoformat()


async def test_daily_rejects_invalid_range(db_client, auth_headers):
    today = today_local()

    reversed_range = await db_client.get(
        f"{STATS_URL}/daily",
        params={"date_from": today.isoformat(), "date_to": (today - timedelta(days=3)).isoformat()},
        headers=auth_headers,
    )
    assert reversed_range.status_code == 400
    assert reversed_range.json()["code"] == "SYS_400"

    too_long = await db_client.get(
        f"{STATS_URL}/daily",
        params={
            "date_from": (today - timedelta(days=400)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers=auth_headers,
    )
    assert too_long.status_code == 400
    assert "365" in too_long.json()["message"]


# ------------------------------------------------------------------ §12.1 科目分布


async def test_subjects_group_by_plan_subject_and_uncategorized(db_client, auth_headers):
    today = today_local()
    plan = await make_plan(db_client, auth_headers, start=today, days=1, subject="高数")
    tasks = await generate_tasks(db_client, auth_headers, plan["id"])

    await complete_task(db_client, auth_headers, tasks[0]["id"], minutes=50)
    await add_record(db_client, auth_headers, minutes=25)  # 不挂任务 → 未分类

    items = (await db_client.get(f"{STATS_URL}/subjects", headers=auth_headers)).json()["items"]
    by_subject = {item["subject"]: item for item in items}

    assert by_subject["高数"]["minutes"] == 50
    assert by_subject["高数"]["task_done"] == 1
    assert by_subject["未分类"]["minutes"] == 25
    assert by_subject["未分类"]["task_done"] == 0


# ------------------------------------------------------------------ §12.1 薄弱知识点


async def test_weak_points_filters_small_samples(db_session, db_client, auth_headers, test_user):
    # 只做过 2 次 → 样本太小，不该被判定为薄弱点
    await seed_quiz(db_session, test_user.id, knowledge="样本不足的知识点", attempts=2, correct=0)
    # 做过 4 次只对 1 次 → 正确率 0.25，应被返回
    await seed_quiz(db_session, test_user.id, knowledge="极限", attempts=4, correct=1)

    items = (
        await db_client.get(f"{STATS_URL}/weak-points", headers=auth_headers)
    ).json()["items"]

    assert [item["knowledge"] for item in items] == ["极限"]
    assert items[0]["attempts"] == 4
    assert items[0]["correct"] == 1
    assert items[0]["accuracy"] == 0.25


async def test_weak_points_respects_limit(db_client, auth_headers, db_session, test_user):
    await seed_quiz(db_session, test_user.id, knowledge="知识点A", attempts=3, correct=0)
    await seed_quiz(db_session, test_user.id, knowledge="知识点B", attempts=3, correct=1)

    items = (
        await db_client.get(f"{STATS_URL}/weak-points?limit=1", headers=auth_headers)
    ).json()["items"]

    assert len(items) == 1
    assert items[0]["knowledge"] == "知识点A"  # 正确率更低（0%）排前面


# ------------------------------------------------------------------ §12.2 推荐


async def test_recommendations_only_habit_for_fresh_account(db_client, auth_headers):
    resp = await db_client.get(RECS_URL, headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["generated_at"]
    # 新账号没有任务/计划/资料，也没学过 → 只剩「降低启动门槛」
    assert [item["kind"] for item in body["items"]] == ["habit"]
    assert body["items"][0]["ref_id"] is None
    assert body["items"][0]["route"].startswith("/")


async def test_recommendations_priority_task_before_review(
    db_client, auth_headers, db_session, test_user
):
    today = today_local()
    # 逾期任务（计划 3 天前开始，任务全在昨天及以前）
    plan = await make_plan(db_client, auth_headers, start=today - timedelta(days=3), days=3)
    await generate_tasks(db_client, auth_headers, plan["id"])
    await seed_quiz(db_session, test_user.id, knowledge="导数", attempts=4, correct=0)

    items = (await db_client.get(RECS_URL, headers=auth_headers)).json()["items"]
    kinds = [item["kind"] for item in items]

    assert kinds[0] == "task"  # 最紧急：先做任务
    assert kinds[1] == "review"  # 其次：补短板
    assert "逾期" in items[0]["reason"]

    review = items[1]
    assert "导数" in review["title"]
    assert review["ref_id"] is None  # 知识点没挂到任何资料时也能返回（route 兜底）


async def test_recommendations_plan_tip_and_material_tip(
    db_client, auth_headers, db_session, test_user
):
    today = today_local()
    await make_plan(db_client, auth_headers, start=today, days=5, status="draft", title="草稿计划")
    await seed_unparsed_material(db_session, test_user.id)

    items = (await db_client.get(RECS_URL, headers=auth_headers)).json()["items"]
    by_kind = {item["kind"]: item for item in items}

    assert "草稿" in by_kind["plan"]["reason"]
    assert "没解析" in by_kind["material"]["reason"] or "解析失败" in by_kind["material"]["reason"]
    assert by_kind["material"]["ref_id"]


async def test_recommendations_respect_limit(db_client, auth_headers):
    today = today_local()
    plan = await make_plan(db_client, auth_headers, start=today - timedelta(days=2), days=2)
    await generate_tasks(db_client, auth_headers, plan["id"])

    items = (await db_client.get(f"{RECS_URL}?limit=1", headers=auth_headers)).json()["items"]

    assert len(items) == 1
    assert items[0]["kind"] == "task"


async def test_recommendations_reject_invalid_limit(db_client, auth_headers):
    resp = await db_client.get(f"{RECS_URL}?limit=0", headers=auth_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


# ------------------------------------------------------------------ 全局异常（M6 验收项）


async def test_unhandled_exception_returns_unified_500_without_stack(
    db_session, test_user, monkeypatch
):
    """未预期异常必须变成 {code:SYS_500}，且**不把堆栈/异常信息**透给前端。"""

    async def _override_get_db():
        yield db_session

    async def boom(*_args, **_kwargs):
        raise RuntimeError("内部实现细节：/etc/passwd 不该出现在响应里")

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(stats_service, "overview", boom)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await login(client, test_user.username, TEST_PASSWORD)
            resp = await client.get(f"{STATS_URL}/overview", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 500
    assert resp.json() == {"code": "SYS_500", "message": "服务内部错误", "detail": None}
    assert "RuntimeError" not in resp.text
    assert "/etc/passwd" not in resp.text
