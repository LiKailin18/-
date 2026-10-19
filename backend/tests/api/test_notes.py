"""在线笔记接口测试（契约：docs/api.md §6）—— 功能 4。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppUser, Material
from app.schemas.user import UserCreate
from app.services import user_service
from tests.conftest import TEST_PASSWORD, login

NOTES_URL = "/api/v1/notes"


async def make_material(
    db: AsyncSession, owner: AppUser, title: str = "测试资料"
) -> Material:
    material = Material(
        user_id=owner.id,
        title=title,
        file_name="fake.pdf",
        file_ext=".pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        file_path=f"{owner.id}/fake.pdf",
        file_hash="a" * 64,
        parse_status="success",
        char_count=100,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material


# ------------------------------------------------------------------ 新建


async def test_create_note_returns_full_object(db_client, auth_headers):
    resp = await db_client.post(
        NOTES_URL,
        json={"title": "极限的两种定义", "content": "ε-δ 定义与序列定义等价。", "tags": ["高数"]},
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "极限的两种定义"
    assert body["content"] == "ε-δ 定义与序列定义等价。"
    assert body["tags"] == ["高数"]
    assert body["material_id"] is None


async def test_create_note_rejects_empty_title(db_client, auth_headers):
    resp = await db_client.post(NOTES_URL, json={"title": "", "content": "x"}, headers=auth_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


async def test_create_note_rejects_oversized_content(db_client, auth_headers):
    resp = await db_client.post(
        NOTES_URL, json={"title": "超长", "content": "x" * 100_001}, headers=auth_headers
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "SYS_422"


async def test_create_note_links_own_material(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    material = await make_material(db_session, test_user)

    resp = await db_client.post(
        NOTES_URL,
        json={"title": "关联资料的笔记", "content": "内容", "material_id": str(material.id)},
        headers=auth_headers,
    )

    assert resp.status_code == 201
    assert resp.json()["material_id"] == str(material.id)


async def test_create_note_rejects_foreign_material(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    """引用别人的资料 → 404（不暴露该资料是否存在）。"""
    other = await user_service.create_user(
        db_session,
        UserCreate(username="note_owner", email="note_owner@example.com", password=TEST_PASSWORD),
    )
    foreign = await make_material(db_session, other, title="别人的资料")

    resp = await db_client.post(
        NOTES_URL,
        json={"title": "偷关联", "content": "x", "material_id": str(foreign.id)},
        headers=auth_headers,
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "SYS_404"


# ------------------------------------------------------------------ 列表


async def test_list_returns_excerpt_without_content(db_client, auth_headers):
    long_content = "极限的定义" * 50  # 250 字
    await db_client.post(
        NOTES_URL, json={"title": "长笔记", "content": long_content}, headers=auth_headers
    )

    resp = await db_client.get(NOTES_URL, headers=auth_headers)

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert "content" not in item
    assert len(item["excerpt"]) <= 121  # 120 字 + 省略号
    assert item["excerpt"].endswith("…")


async def test_list_searches_title_and_content(db_client, auth_headers):
    await db_client.post(
        NOTES_URL, json={"title": "线性代数", "content": "矩阵的秩"}, headers=auth_headers
    )
    await db_client.post(
        NOTES_URL, json={"title": "概率论", "content": "贝叶斯公式"}, headers=auth_headers
    )

    by_title = await db_client.get(f"{NOTES_URL}?keyword=概率", headers=auth_headers)
    assert by_title.json()["total"] == 1
    assert by_title.json()["items"][0]["title"] == "概率论"

    by_content = await db_client.get(f"{NOTES_URL}?keyword=贝叶斯", headers=auth_headers)
    assert by_content.json()["total"] == 1


async def test_list_filters_by_tag_and_material(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    material = await make_material(db_session, test_user)
    await db_client.post(
        NOTES_URL,
        json={"title": "带标签", "content": "x", "tags": ["重点", "复习"]},
        headers=auth_headers,
    )
    await db_client.post(
        NOTES_URL,
        json={"title": "关联资料", "content": "y", "material_id": str(material.id)},
        headers=auth_headers,
    )

    by_tag = await db_client.get(f"{NOTES_URL}?tag=重点", headers=auth_headers)
    assert by_tag.json()["total"] == 1
    assert by_tag.json()["items"][0]["title"] == "带标签"

    by_material = await db_client.get(
        f"{NOTES_URL}?material_id={material.id}", headers=auth_headers
    )
    assert by_material.json()["total"] == 1
    assert by_material.json()["items"][0]["title"] == "关联资料"


async def test_list_pagination(db_client, auth_headers):
    for index in range(3):
        await db_client.post(
            NOTES_URL, json={"title": f"笔记 {index}", "content": "x"}, headers=auth_headers
        )

    resp = await db_client.get(f"{NOTES_URL}?page=1&size=2", headers=auth_headers)

    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


# ------------------------------------------------------------------ 详情 / 修改 / 删除


async def test_get_note_returns_content(db_client, auth_headers):
    created = await db_client.post(
        NOTES_URL, json={"title": "详情", "content": "完整正文在这里"}, headers=auth_headers
    )

    resp = await db_client.get(f"{NOTES_URL}/{created.json()['id']}", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["content"] == "完整正文在这里"


async def test_patch_note_updates_fields(db_client, auth_headers):
    created = await db_client.post(
        NOTES_URL, json={"title": "旧标题", "content": "旧内容"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    resp = await db_client.patch(
        f"{NOTES_URL}/{note_id}",
        json={"title": "新标题", "tags": ["已整理"]},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "新标题"
    assert resp.json()["tags"] == ["已整理"]
    # 未提交的字段保持不变
    assert resp.json()["content"] == "旧内容"


async def test_patch_note_rejects_foreign_material(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    other = await user_service.create_user(
        db_session,
        UserCreate(username="note_owner2", email="note_owner2@example.com", password=TEST_PASSWORD),
    )
    foreign = await make_material(db_session, other, title="别人的资料2")
    created = await db_client.post(
        NOTES_URL, json={"title": "笔记", "content": "x"}, headers=auth_headers
    )

    resp = await db_client.patch(
        f"{NOTES_URL}/{created.json()['id']}",
        json={"material_id": str(foreign.id)},
        headers=auth_headers,
    )

    assert resp.status_code == 404


async def test_delete_note_is_soft_delete(db_client, auth_headers):
    created = await db_client.post(
        NOTES_URL, json={"title": "待删除", "content": "x"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    deleted = await db_client.delete(f"{NOTES_URL}/{note_id}", headers=auth_headers)
    assert deleted.status_code == 204

    gone = await db_client.get(f"{NOTES_URL}/{note_id}", headers=auth_headers)
    assert gone.status_code == 404

    listing = await db_client.get(NOTES_URL, headers=auth_headers)
    assert all(item["id"] != note_id for item in listing.json()["items"])


# ------------------------------------------------------------------ 隔离


async def test_notes_are_isolated_between_users(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    created = await db_client.post(
        NOTES_URL, json={"title": "私密笔记", "content": "secret"}, headers=auth_headers
    )
    note_id = created.json()["id"]

    await user_service.create_user(
        db_session,
        UserCreate(
            username="note_intruder",
            email="note_intruder@example.com",
            password=TEST_PASSWORD,
        ),
    )
    intruder = await login(db_client, "note_intruder", TEST_PASSWORD)

    # 别人的笔记：读不到、改不了、删不掉，且列表里也看不到
    assert (await db_client.get(f"{NOTES_URL}/{note_id}", headers=intruder)).status_code == 404
    assert (
        await db_client.patch(f"{NOTES_URL}/{note_id}", json={"title": "x"}, headers=intruder)
    ).status_code == 404
    assert (await db_client.delete(f"{NOTES_URL}/{note_id}", headers=intruder)).status_code == 404

    their_list = await db_client.get(NOTES_URL, headers=intruder)
    assert their_list.json()["total"] == 0
