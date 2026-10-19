"""学习任务接口测试（契约：docs/api.md §8）—— 功能 6。"""

import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StudyRecord
from app.schemas.user import UserCreate
from app.services import user_service
from tests.conftest import TEST_PASSWORD, login

TASKS_URL = "/api/v1/tasks"
PLANS_URL = "/api/v1/plans"


async def create_plan_with_tasks(db_client, auth_headers, days: int = 3) -> tuple[dict, list[dict]]:
    start = date(2026, 11, 1)
    plan = (
        await db_client.post(
            PLANS_URL,
            json={
                "title": "任务测试计划",
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=days - 1)).isoformat(),
                "daily_minutes": 45,
            },
            headers=auth_headers,
        )
    ).json()
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers)
    tasks = (
        await db_client.get(f"{TASKS_URL}?plan_id={plan['id']}", headers=auth_headers)
    ).json()["items"]
    return plan, tasks


# ------------------------------------------------------------------ 列表与新建


async def test_list_tasks_filters_by_date_and_status(db_client, auth_headers):
    plan, _tasks = await create_plan_with_tasks(db_client, auth_headers, days=3)

    by_plan = await db_client.get(f"{TASKS_URL}?plan_id={plan['id']}", headers=auth_headers)
    assert by_plan.json()["total"] == 3

    by_date = await db_client.get(f"{TASKS_URL}?plan_date=2026-11-02", headers=auth_headers)
    assert by_date.json()["total"] == 1

    by_range = await db_client.get(
        f"{TASKS_URL}?date_from=2026-11-02&date_to=2026-11-03", headers=auth_headers
    )
    assert by_range.json()["total"] == 2

    by_status = await db_client.get(f"{TASKS_URL}?status=pending", headers=auth_headers)
    assert by_status.json()["total"] == 3


async def test_create_standalone_task(db_client, auth_headers):
    resp = await db_client.post(
        TASKS_URL,
        json={"plan_date": "2026-11-10", "title": "复习英语单词", "est_minutes": 30},
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["plan_id"] is None
    assert body["title"] == "复习英语单词"
    assert body["status"] == "pending"
    assert body["order_no"] == 1


async def test_create_task_conflicts_on_same_plan_date(
    db_client, db_session: AsyncSession, auth_headers
):
    """同一计划同一天只能有一条任务（部分唯一索引）。"""
    plan, _ = await create_plan_with_tasks(db_client, auth_headers, days=1)

    resp = await db_client.post(
        TASKS_URL,
        json={
            "plan_id": plan["id"],
            "plan_date": "2026-11-01",
            "title": "重复的一天",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "PLAN_001"


async def test_create_task_rejects_foreign_plan(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    await user_service.create_user(
        db_session,
        UserCreate(username="task_owner", email="task_owner@example.com", password=TEST_PASSWORD),
    )
    foreign_plan = (
        await db_client.post(
            PLANS_URL,
            json={
                "title": "别人的计划",
                "start_date": "2026-11-01",
                "end_date": "2026-11-02",
            },
            headers=await login(db_client, "task_owner", TEST_PASSWORD),
        )
    ).json()

    resp = await db_client.post(
        TASKS_URL,
        json={"plan_id": foreign_plan["id"], "plan_date": "2026-11-05", "title": "偷建任务"},
        headers=auth_headers,
    )

    assert resp.status_code == 404


# ------------------------------------------------------------------ 修改与完成


async def test_patch_task_sets_and_clears_completed_at(db_client, auth_headers):
    _, tasks = await create_plan_with_tasks(db_client, auth_headers, days=1)
    task_id = tasks[0]["id"]

    done = await db_client.patch(
        f"{TASKS_URL}/{task_id}", json={"status": "done"}, headers=auth_headers
    )
    assert done.status_code == 200
    assert done.json()["completed_at"] is not None

    back = await db_client.patch(
        f"{TASKS_URL}/{task_id}", json={"status": "pending"}, headers=auth_headers
    )
    assert back.json()["completed_at"] is None


async def test_complete_task_creates_study_record_atomically(
    db_client, db_session: AsyncSession, auth_headers
):
    _, tasks = await create_plan_with_tasks(db_client, auth_headers, days=1)
    task_id = tasks[0]["id"]

    resp = await db_client.post(
        f"{TASKS_URL}/{task_id}/complete",
        json={"duration_minutes": 55, "content": "看完第一章并做完例题"},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task"]["status"] == "done"
    assert body["task"]["completed_at"] is not None
    assert body["study_record_id"] is not None

    record = await db_session.get(StudyRecord, uuid.UUID(body["study_record_id"]))
    assert record is not None
    assert record.duration_minutes == 55
    assert record.task_id == uuid.UUID(task_id)
    assert record.type == "other"  # 自动记录的类型口径
    assert "第一章" in (record.content or "")


async def test_complete_task_without_record(db_client, auth_headers):
    _, tasks = await create_plan_with_tasks(db_client, auth_headers, days=1)

    resp = await db_client.post(
        f"{TASKS_URL}/{tasks[0]['id']}/complete",
        json={"duration_minutes": 30, "create_record": False},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["study_record_id"] is None


async def test_complete_task_twice_rejected(db_client, auth_headers):
    _, tasks = await create_plan_with_tasks(db_client, auth_headers, days=1)
    task_id = tasks[0]["id"]
    await db_client.post(
        f"{TASKS_URL}/{task_id}/complete", json={"duration_minutes": 30}, headers=auth_headers
    )

    again = await db_client.post(
        f"{TASKS_URL}/{task_id}/complete", json={"duration_minutes": 30}, headers=auth_headers
    )

    assert again.status_code == 400
    assert again.json()["code"] == "SYS_400"


async def test_delete_task(db_client, auth_headers):
    _, tasks = await create_plan_with_tasks(db_client, auth_headers, days=1)
    task_id = tasks[0]["id"]

    deleted = await db_client.delete(f"{TASKS_URL}/{task_id}", headers=auth_headers)
    assert deleted.status_code == 204

    gone = await db_client.patch(f"{TASKS_URL}/{task_id}", json={}, headers=auth_headers)
    assert gone.status_code == 404


# ------------------------------------------------------------------ 隔离


async def test_tasks_are_isolated_between_users(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    _, tasks = await create_plan_with_tasks(db_client, auth_headers, days=1)
    task_id = tasks[0]["id"]

    await user_service.create_user(
        db_session,
        UserCreate(
            username="task_intruder", email="task_intruder@example.com", password=TEST_PASSWORD
        ),
    )
    intruder = await login(db_client, "task_intruder", TEST_PASSWORD)

    assert (await db_client.get(TASKS_URL, headers=intruder)).json()["total"] == 0
    assert (
        await db_client.patch(f"{TASKS_URL}/{task_id}", json={"status": "done"}, headers=intruder)
    ).status_code == 404
    assert (
        await db_client.post(
            f"{TASKS_URL}/{task_id}/complete", json={}, headers=intruder
        )
    ).status_code == 404
