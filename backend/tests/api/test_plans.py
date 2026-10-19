"""学习计划接口测试（契约：docs/api.md §7）—— 功能 5。

重点覆盖「生成每日任务的幂等性」：
它是靠 study_task 的部分唯一索引实现的（含 deleted_at IS NULL），
所以「删掉某天的任务后能重新生成」也必须成立。
"""


from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserCreate
from app.services import user_service
from tests.conftest import TEST_PASSWORD, login

PLANS_URL = "/api/v1/plans"


def plan_body(**overrides) -> dict:
    body = {
        "title": "高数期末冲刺",
        "subject": "高数",
        "goal": "期末 85+",
        "start_date": "2026-11-01",
        "end_date": "2026-11-05",
        "daily_minutes": 60,
    }
    body.update(overrides)
    return body


async def create_plan(db_client, auth_headers, **overrides) -> dict:
    resp = await db_client.post(PLANS_URL, json=plan_body(**overrides), headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------------------ 创建与校验


async def test_create_plan_returns_contract_fields(db_client, auth_headers):
    body = await create_plan(db_client, auth_headers)

    assert body["title"] == "高数期末冲刺"
    assert body["start_date"] == "2026-11-01"
    assert body["end_date"] == "2026-11-05"
    assert body["daily_minutes"] == 60
    assert body["status"] == "active"
    assert body["progress"] == {"task_total": 0, "task_done": 0, "progress": 0.0}


async def test_create_plan_rejects_reversed_dates(db_client, auth_headers):
    resp = await db_client.post(
        PLANS_URL,
        json=plan_body(start_date="2026-11-05", end_date="2026-11-01"),
        headers=auth_headers,
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


async def test_create_plan_rejects_range_over_180_days(db_client, auth_headers):
    resp = await db_client.post(
        PLANS_URL,
        json=plan_body(start_date="2026-01-01", end_date="2026-08-01"),
        headers=auth_headers,
    )

    assert resp.status_code == 422


async def test_create_plan_rejects_foreign_material(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    from tests.api.test_notes import make_material

    other = await user_service.create_user(
        db_session,
        UserCreate(username="plan_owner", email="plan_owner@example.com", password=TEST_PASSWORD),
    )
    foreign = await make_material(db_session, other, title="别人的资料")

    resp = await db_client.post(
        PLANS_URL, json=plan_body(material_ids=[str(foreign.id)]), headers=auth_headers
    )

    assert resp.status_code == 404


# ------------------------------------------------------------------ 列表与详情


async def test_list_plans_supports_status_filter(db_client, auth_headers):
    await create_plan(db_client, auth_headers, title="计划A", status="active")
    await create_plan(db_client, auth_headers, title="计划B", status="archived")

    all_plans = await db_client.get(PLANS_URL, headers=auth_headers)
    assert all_plans.json()["total"] == 2

    only_active = await db_client.get(f"{PLANS_URL}?status=active", headers=auth_headers)
    assert only_active.json()["total"] == 1
    assert only_active.json()["items"][0]["title"] == "计划A"


async def test_plan_detail_includes_materials(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    from tests.api.test_notes import make_material

    material = await make_material(db_session, test_user, title="高数第一章")
    plan = await create_plan(db_client, auth_headers, material_ids=[str(material.id)])

    resp = await db_client.get(f"{PLANS_URL}/{plan['id']}", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["material_ids"] == [str(material.id)]
    assert body["materials"][0]["title"] == "高数第一章"
    assert set(body["materials"][0]) == {"id", "title", "subject"}


# ------------------------------------------------------------------ 修改与删除


async def test_patch_plan_updates_allowed_fields(db_client, auth_headers):
    plan = await create_plan(db_client, auth_headers)

    resp = await db_client.patch(
        f"{PLANS_URL}/{plan['id']}",
        json={"title": "改名", "daily_minutes": 90, "status": "archived"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "改名"
    assert resp.json()["daily_minutes"] == 90
    assert resp.json()["status"] == "archived"


async def test_patch_plan_rejects_date_change(db_client, auth_headers):
    """契约：计划区间不可改（会让已生成的任务与区间不一致）。"""
    plan = await create_plan(db_client, auth_headers)

    resp = await db_client.patch(
        f"{PLANS_URL}/{plan['id']}", json={"start_date": "2026-12-01"}, headers=auth_headers
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "SYS_400"


async def test_delete_plan_soft_deletes_pending_tasks_only(
    db_client, db_session: AsyncSession, auth_headers
):
    plan = await create_plan(db_client, auth_headers)
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers)

    tasks = (
        await db_client.get(f"/api/v1/tasks?plan_id={plan['id']}", headers=auth_headers)
    ).json()["items"]
    first = tasks[-1]
    await db_client.post(
        f"/api/v1/tasks/{first['id']}/complete",
        json={"duration_minutes": 30, "create_record": False},
        headers=auth_headers,
    )

    deleted = await db_client.delete(f"{PLANS_URL}/{plan['id']}", headers=auth_headers)
    assert deleted.status_code == 204

    remaining = (
        await db_client.get(f"/api/v1/tasks?plan_id={plan['id']}", headers=auth_headers)
    ).json()
    completed = (
        await db_client.get(
            f"/api/v1/tasks?plan_id={plan['id']}&status=done", headers=auth_headers
        )
    ).json()

    # 未完成的被级联软删，已完成（用于统计）保留
    assert remaining["total"] == 0 or all(
        item["status"] == "done" for item in remaining["items"]
    )
    assert completed["total"] == 1


# ------------------------------------------------------------------ 生成每日任务


async def test_generate_tasks_creates_one_per_day(db_client, auth_headers):
    plan = await create_plan(db_client, auth_headers)  # 11-01 ~ 11-05 = 5 天

    resp = await db_client.post(
        f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] == 5
    assert body["skipped"] == 0
    assert len(body["dates"]) == 5

    tasks = (
        await db_client.get(f"/api/v1/tasks?plan_id={plan['id']}", headers=auth_headers)
    ).json()
    assert tasks["total"] == 5
    assert {item["plan_date"] for item in tasks["items"]} == {
        "2026-11-01",
        "2026-11-02",
        "2026-11-03",
        "2026-11-04",
        "2026-11-05",
    }
    assert all(item["status"] == "pending" for item in tasks["items"])


async def test_generate_tasks_is_idempotent(db_client, auth_headers):
    """全部已存在 → 409 PLAN_001（而不是静默成功让用户以为又生成了）。"""
    plan = await create_plan(db_client, auth_headers)
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers)

    again = await db_client.post(
        f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers
    )

    assert again.status_code == 409
    assert again.json()["code"] == "PLAN_001"


async def test_generate_tasks_backfills_deleted_day(
    db_client, db_session: AsyncSession, auth_headers
):
    """删掉某天的任务后可以重新生成 —— 这正是「部分唯一索引」相对普通 UNIQUE 的价值。"""
    plan = await create_plan(db_client, auth_headers)
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers)

    tasks = (
        await db_client.get(f"/api/v1/tasks?plan_id={plan['id']}", headers=auth_headers)
    ).json()["items"]
    victim = tasks[0]
    await db_client.delete(f"/api/v1/tasks/{victim['id']}", headers=auth_headers)

    resp = await db_client.post(
        f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers
    )

    assert resp.status_code == 201
    assert resp.json()["created"] == 1
    assert resp.json()["skipped"] == 4
    assert resp.json()["dates"] == [victim["plan_date"]]


async def test_generate_tasks_overwrite_rebuilds_pending(
    db_client, db_session: AsyncSession, auth_headers
):
    plan = await create_plan(db_client, auth_headers)
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers)

    tasks = (
        await db_client.get(f"/api/v1/tasks?plan_id={plan['id']}", headers=auth_headers)
    ).json()["items"]
    await db_client.post(
        f"/api/v1/tasks/{tasks[0]['id']}/complete",
        json={"duration_minutes": 20, "create_record": False},
        headers=auth_headers,
    )

    resp = await db_client.post(
        f"{PLANS_URL}/{plan['id']}/generate-tasks", json={"overwrite": True}, headers=auth_headers
    )

    assert resp.status_code == 201
    # 已完成的保留，其余 4 天重建
    assert resp.json()["created"] == 4
    assert resp.json()["skipped"] == 1


async def test_plan_progress_reflects_completed_tasks(db_client, auth_headers):
    plan = await create_plan(db_client, auth_headers)
    await db_client.post(f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=auth_headers)
    tasks = (
        await db_client.get(f"/api/v1/tasks?plan_id={plan['id']}", headers=auth_headers)
    ).json()["items"]
    for task in tasks[:2]:
        await db_client.post(
            f"/api/v1/tasks/{task['id']}/complete",
            json={"duration_minutes": 30, "create_record": False},
            headers=auth_headers,
        )

    detail = await db_client.get(f"{PLANS_URL}/{plan['id']}", headers=auth_headers)

    progress = detail.json()["progress"]
    assert progress["task_total"] == 5
    assert progress["task_done"] == 2
    assert progress["progress"] == 0.4


# ------------------------------------------------------------------ 隔离


async def test_plans_are_isolated_between_users(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    plan = await create_plan(db_client, auth_headers)

    await user_service.create_user(
        db_session,
        UserCreate(
            username="plan_intruder",
            email="plan_intruder@example.com",
            password=TEST_PASSWORD,
        ),
    )
    intruder = await login(db_client, "plan_intruder", TEST_PASSWORD)

    assert (await db_client.get(f"{PLANS_URL}/{plan['id']}", headers=intruder)).status_code == 404
    assert (
        await db_client.post(
            f"{PLANS_URL}/{plan['id']}/generate-tasks", json={}, headers=intruder
        )
    ).status_code == 404
    assert (
        await db_client.patch(f"{PLANS_URL}/{plan['id']}", json={"title": "x"}, headers=intruder)
    ).status_code == 404
    assert (await db_client.get(PLANS_URL, headers=intruder)).json()["total"] == 0
