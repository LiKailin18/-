"""学习记录接口测试（契约：docs/api.md §9）—— 功能 12。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserCreate
from app.services import user_service
from app.utils.time import today_local
from tests.conftest import TEST_PASSWORD, login

RECORDS_URL = "/api/v1/study-records"
PLANS_URL = "/api/v1/plans"
TASKS_URL = "/api/v1/tasks"


def record_body(**overrides) -> dict:
    body = {
        "type": "reading",
        "started_at": datetime.now(UTC).isoformat(),
        "duration_minutes": 45,
        "content": "读高数第一章",
    }
    body.update(overrides)
    return body


# ------------------------------------------------------------------ 创建与校验


async def test_create_record_returns_contract_fields(db_client, auth_headers):
    resp = await db_client.post(RECORDS_URL, json=record_body(), headers=auth_headers)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "reading"
    assert body["duration_minutes"] == 45
    assert body["content"] == "读高数第一章"
    assert body["task_id"] is None and body["material_id"] is None


async def test_create_record_rejects_future_start_time(db_client, auth_headers):
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    resp = await db_client.post(
        RECORDS_URL, json=record_body(started_at=future), headers=auth_headers
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


async def test_create_record_tolerates_small_clock_skew(db_client, auth_headers):
    """客户端时钟快 2 分钟不应被拒（容忍 5 分钟）。"""
    skewed = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()

    resp = await db_client.post(
        RECORDS_URL, json=record_body(started_at=skewed), headers=auth_headers
    )

    assert resp.status_code == 201


async def test_create_record_validates_duration(db_client, auth_headers):
    for bad in (0, -5, 1441):
        resp = await db_client.post(
            RECORDS_URL, json=record_body(duration_minutes=bad), headers=auth_headers
        )
        assert resp.status_code == 422, bad


async def test_create_record_rejects_foreign_task(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    other_headers = await login(db_client, "record_owner", TEST_PASSWORD) if False else None
    other = await user_service.create_user(
        db_session,
        UserCreate(
            username="record_owner", email="record_owner@example.com", password=TEST_PASSWORD
        ),
    )
    other_headers = await login(db_client, other.username, TEST_PASSWORD)
    plan = (
        await db_client.post(
            PLANS_URL,
            json={"title": "别人的计划", "start_date": "2026-11-01", "end_date": "2026-11-01"},
            headers=other_headers,
        )
    ).json()
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=other_headers)
    foreign_task = (
        await db_client.get(f"{TASKS_URL}?plan_id={plan['id']}", headers=other_headers)
    ).json()["items"][0]

    resp = await db_client.post(
        RECORDS_URL, json=record_body(task_id=foreign_task["id"]), headers=auth_headers
    )

    assert resp.status_code == 404


# ------------------------------------------------------------------ 列表过滤


async def test_list_records_filters_by_date_type_and_plan(
    db_client, db_session: AsyncSession, auth_headers
):
    now = datetime.now(UTC)
    await db_client.post(RECORDS_URL, json=record_body(type="reading"), headers=auth_headers)
    await db_client.post(
        RECORDS_URL,
        json=record_body(type="video", started_at=(now - timedelta(days=10)).isoformat()),
        headers=auth_headers,
    )

    by_type = await db_client.get(f"{RECORDS_URL}?type=video", headers=auth_headers)
    assert by_type.json()["total"] == 1

    # 按业务时区的「今天」过滤：UTC 与东八区可能不在同一天，这里必须都能命中
    today = today_local().isoformat()
    by_date = await db_client.get(
        f"{RECORDS_URL}?date_from={today}&date_to={today}", headers=auth_headers
    )
    assert by_date.json()["total"] == 1
    assert by_date.json()["items"][0]["type"] == "reading"


async def test_list_records_filters_by_plan_via_task(
    db_client, auth_headers
):
    start = today_local()
    plan = (
        await db_client.post(
            PLANS_URL,
            json={
                "title": "记录过滤计划",
                "start_date": start.isoformat(),
                "end_date": start.isoformat(),
            },
            headers=auth_headers,
        )
    ).json()
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers)
    task = (
        await db_client.get(f"{TASKS_URL}?plan_id={plan['id']}", headers=auth_headers)
    ).json()["items"][0]

    # 完成任务会自动写一条带 task_id 的记录
    completed = await db_client.post(
        f"{TASKS_URL}/{task['id']}/complete",
        json={"duration_minutes": 25, "content": "完成当日任务"},
        headers=auth_headers,
    )
    record_id = completed.json()["study_record_id"]

    by_plan = await db_client.get(f"{RECORDS_URL}?plan_id={plan['id']}", headers=auth_headers)

    assert by_plan.json()["total"] == 1
    assert by_plan.json()["items"][0]["id"] == record_id


# ------------------------------------------------------------------ 修改与删除


async def test_patch_record(db_client, auth_headers):
    created = (
        await db_client.post(RECORDS_URL, json=record_body(), headers=auth_headers)
    ).json()

    resp = await db_client.patch(
        f"{RECORDS_URL}/{created['id']}",
        json={"duration_minutes": 90, "type": "review", "content": "改过的备注"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["duration_minutes"] == 90
    assert resp.json()["type"] == "review"
    assert resp.json()["content"] == "改过的备注"


async def test_delete_record(db_client, auth_headers):
    created = (
        await db_client.post(RECORDS_URL, json=record_body(), headers=auth_headers)
    ).json()

    assert (
        await db_client.delete(f"{RECORDS_URL}/{created['id']}", headers=auth_headers)
    ).status_code == 204

    listing = await db_client.get(RECORDS_URL, headers=auth_headers)
    assert all(item["id"] != created["id"] for item in listing.json()["items"])


# ------------------------------------------------------------------ 隔离


async def test_records_are_isolated_between_users(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    created = (
        await db_client.post(RECORDS_URL, json=record_body(), headers=auth_headers)
    ).json()

    await user_service.create_user(
        db_session,
        UserCreate(
            username="record_intruder",
            email="record_intruder@example.com",
            password=TEST_PASSWORD,
        ),
    )
    intruder = await login(db_client, "record_intruder", TEST_PASSWORD)

    assert (await db_client.get(RECORDS_URL, headers=intruder)).json()["total"] == 0
    assert (
        await db_client.patch(
            f"{RECORDS_URL}/{created['id']}", json={"duration_minutes": 1}, headers=intruder
        )
    ).status_code == 404
    assert (
        await db_client.delete(f"{RECORDS_URL}/{created['id']}", headers=intruder)
    ).status_code == 404
