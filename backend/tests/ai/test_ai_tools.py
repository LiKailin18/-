"""Agent 工具测试（契约：docs/agent-tools.md §1–§3）。

工具直接调用（绕过模型），重点验证：
- 统一信封结构与截断
- **user_id 由闭包注入** → 跨用户不可见
- 失败返回 {"ok": false} 而不是抛异常
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools import (
    make_get_study_stats,
    make_get_weak_points,
    make_list_materials,
    make_list_pending_tasks,
    make_read_material_chunk,
    make_search_material,
)
from app.models import AppUser, Material, Quiz, QuizAttempt
from app.schemas.user import UserCreate
from app.services import user_service
from tests.conftest import TEST_PASSWORD


async def make_material(
    db: AsyncSession,
    owner: AppUser,
    *,
    title: str = "高数第一章",
    text: str = "极限的定义：如果存在常数 A，当 x 趋于 x0 时 f(x) 趋于 A。",
    parse_status: str = "success",
) -> Material:
    material = Material(
        user_id=owner.id,
        title=title,
        subject="高数",
        file_name="chapter1.pdf",
        file_ext=".pdf",
        mime_type="application/pdf",
        size_bytes=2048,
        file_path=f"{owner.id}/fake.pdf",
        file_hash=uuid.uuid4().hex * 2,
        parse_status=parse_status,
        char_count=len(text),
        extracted_text=text,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material


# --------------------------------------------------------------------- 资料类工具


async def test_list_materials_only_returns_parsed_ones(db_session: AsyncSession, test_user):
    await make_material(db_session, test_user, title="已解析")
    await make_material(db_session, test_user, title="还没解析完", parse_status="pending")

    tool = make_list_materials(test_user.id, db_session)
    result = await tool.ainvoke({})

    assert result["ok"] is True
    titles = [item["title"] for item in result["data"]["materials"]]
    assert titles == ["已解析"]
    assert result["meta"]["count"] == 1
    # 工具不得返回内部字段
    assert "extracted_text" not in result["data"]["materials"][0]
    assert "file_path" not in result["data"]["materials"][0]


async def test_search_material_returns_snippet_and_respects_limits(
    db_session: AsyncSession, test_user
):
    await make_material(db_session, test_user, text="开头" * 400 + "极限的定义" + "结尾" * 400)

    tool = make_search_material(test_user.id, db_session)
    result = await tool.ainvoke({"keyword": "极限"})

    assert result["ok"] is True
    hit = result["data"]["hits"][0]
    assert "极限" in hit["snippet"]
    assert len(hit["snippet"]) <= 600
    assert hit["offset"] > 0


async def test_search_material_empty_result_is_not_an_error(
    db_session: AsyncSession, test_user
):
    tool = make_search_material(test_user.id, db_session)
    result = await tool.ainvoke({"keyword": "不存在的词"})

    assert result["ok"] is True
    assert result["data"]["hits"] == []


async def test_search_material_escapes_like_wildcards(db_session: AsyncSession, test_user):
    """`%` 不能被当作通配符（否则等于返回全部内容）。"""
    await make_material(db_session, test_user, text="普通内容，没有百分号")

    tool = make_search_material(test_user.id, db_session)
    result = await tool.ainvoke({"keyword": "%"})

    assert result["data"]["hits"] == []


async def test_read_material_chunk_pages_and_blocks_other_users(
    db_session: AsyncSession, test_user
):
    material = await make_material(db_session, test_user, text="0123456789")

    tool = make_read_material_chunk(test_user.id, db_session)
    first = await tool.ainvoke({"material_id": str(material.id), "offset": 0, "limit": 4})
    assert first["ok"] is True
    assert first["data"]["text"] == "0123"
    assert first["data"]["has_more"] is True

    # 别人的用户 id 读同一份资料 → 统一错误（不暴露存在性）
    stranger = uuid.uuid4()
    blocked = await make_read_material_chunk(stranger, db_session).ainvoke(
        {"material_id": str(material.id)}
    )
    assert blocked["ok"] is False
    assert blocked["error"] == "MATERIAL_NOT_FOUND"


async def test_read_material_chunk_rejects_bad_uuid(db_session: AsyncSession, test_user):
    tool = make_read_material_chunk(test_user.id, db_session)
    result = await tool.ainvoke({"material_id": "not-a-uuid"})

    assert result["ok"] is False
    assert result["error"] == "BAD_ID"


async def test_read_material_chunk_truncates_beyond_max(
    db_session: AsyncSession, test_user
):
    material = await make_material(db_session, test_user, text="汉" * 6000)

    tool = make_read_material_chunk(test_user.id, db_session)
    result = await tool.ainvoke({"material_id": str(material.id), "limit": 4000})

    assert result["meta"]["truncated"] is True
    assert len(result["data"]["text"]) == 4000


# --------------------------------------------------------------------- 数据类工具


async def test_get_study_stats_returns_aggregates(db_session: AsyncSession, test_user):
    tool = make_get_study_stats(test_user.id, db_session)
    result = await tool.ainvoke({"days": 7})

    assert result["ok"] is True
    data = result["data"]
    assert data["total_minutes"] == 0
    assert data["task_completion_rate"] == 0.0  # 无数据时为 0，不是 null
    assert "period" in data


async def test_get_weak_points_requires_enough_samples(
    db_session: AsyncSession, test_user
):
    """样本少于 3 次的知识点不返回（避免给出误导性建议）。"""
    quiz = Quiz(
        user_id=test_user.id,
        title="测验",
        question_count=1,
        types=["single"],
        difficulty="medium",
        question_data=[
            {
                "no": 1,
                "type": "single",
                "stem": "题目？",
                "options": ["A", "B", "C", "D"],
                "answer": ["A"],
                "explanation": "解析",
                "knowledge": "极限",
            }
        ],
        model="fake",
    )
    db_session.add(quiz)
    await db_session.commit()
    await db_session.refresh(quiz)

    # 只有 2 次作答 → 样本不足
    for _ in range(2):
        db_session.add(
            QuizAttempt(
                quiz_id=quiz.id,
                user_id=test_user.id,
                answers=[{"no": 1, "answer": ["B"], "is_correct": False}],
                score=0,
                correct_count=0,
                question_count=1,
            )
        )
    await db_session.commit()

    tool = make_get_weak_points(test_user.id, db_session)
    result = await tool.ainvoke({})
    assert result["data"]["weak_points"] == []

    # 补到 3 次后出现，且正确率为 0
    db_session.add(
        QuizAttempt(
            quiz_id=quiz.id,
            user_id=test_user.id,
            answers=[{"no": 1, "answer": ["A"], "is_correct": True}],
            score=100,
            correct_count=1,
            question_count=1,
        )
    )
    await db_session.commit()

    result2 = await tool.ainvoke({})
    points = result2["data"]["weak_points"]
    assert len(points) == 1
    assert points[0]["knowledge"] == "极限"
    assert points[0]["attempts"] == 3
    assert points[0]["accuracy"] == 0.3333


async def test_list_pending_tasks_defaults_to_today_and_validates_input(
    db_session: AsyncSession, test_user
):
    tool = make_list_pending_tasks(test_user.id, db_session)

    ok = await tool.ainvoke({})
    assert ok["ok"] is True
    assert ok["data"]["tasks"] == []

    bad_date = await tool.ainvoke({"plan_date": "2026/10/20"})
    assert bad_date["ok"] is False
    assert bad_date["error"] == "BAD_DATE"

    bad_status = await tool.ainvoke({"status": "unknown"})
    assert bad_status["ok"] is False
    assert bad_status["error"] == "BAD_STATUS"


async def test_tools_do_not_see_other_users_data(
    db_session: AsyncSession, test_user
):
    other = await user_service.create_user(
        db_session,
        UserCreate(username="tool_other", email="tool_other@example.com", password=TEST_PASSWORD),
    )
    await make_material(db_session, other, title="别人的资料", text="别人的内容")

    listing = await make_list_materials(test_user.id, db_session).ainvoke({})
    assert listing["data"]["materials"] == []

    search = await make_search_material(test_user.id, db_session).ainvoke({"keyword": "别人"})
    assert search["data"]["hits"] == []
