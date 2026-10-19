"""AI 接口测试（契约：docs/api.md §10、§11、§14）—— 用 fake model 打桩，不打真实模型。

打桩点选在 `app.services.ai_common.invoke_structured`：
这样「配额 → 调用 → 业务二次校验 → 落库 → 记录用量」这条真实链路仍然被测到，
只有模型本身是假的。
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime import AgentUsage
from app.ai.schemas import AdviceOut, AdviceSuggestion, QuizOut, QuizQuestion, SummaryOut
from app.core.config import settings
from app.models import AiGeneration, AiUsage, Material
from app.services import ai_common, chat_service
from tests.ai.test_ai_tools import make_material
from tests.conftest import TEST_PASSWORD, login

SUMMARIES_URL = "/api/v1/ai/summaries"
QUIZZES_URL = "/api/v1/quizzes"
GENERATE_QUIZ_URL = "/api/v1/ai/quizzes"
ADVICE_URL = "/api/v1/ai/advice"
USAGE_URL = "/api/v1/ai/usage"
SESSIONS_URL = "/api/v1/ai/chat-sessions"

FAKE_USAGE = AgentUsage(prompt_tokens=120, completion_tokens=80, steps=2, latency_ms=1500)


def fake_summary() -> SummaryOut:
    return SummaryOut(
        summary_md="## 一、极限的定义\n函数在某点的极限描述了函数值的趋近行为。",
        key_points=["ε-δ 定义", "左右极限"],
    )


def fake_quiz(count: int = 2, types: list[str] | None = None) -> QuizOut:
    types = types or ["single"]
    questions = []
    for index in range(1, count + 1):
        if types[0] == "judge":
            questions.append(
                QuizQuestion(
                    no=index,
                    type="judge",
                    options=["正确", "错误"],
                    stem=f"第 {index} 题：极限一定存在吗？",
                    answer=["错误"],
                    explanation="需要左右极限都存在且相等。",
                    knowledge="极限存在性",
                )
            )
        else:
            questions.append(
                QuizQuestion(
                    no=index,
                    type="single",
                    stem=f"第 {index} 题：连续的充要条件是什么？",
                    options=["A 选项", "B 选项", "C 选项", "D 选项"],
                    answer=["B 选项"],
                    explanation="左右极限等于函数值。",
                    knowledge="函数的连续性",
                )
            )
    return QuizOut(title="第一章测验", questions=questions)


def fake_advice() -> AdviceOut:
    return AdviceOut(
        summary="近 7 天学习 3.2 小时，任务完成率 78%，正确率 61%，建议优先补极限。",
        suggestions=[
            AdviceSuggestion(
                title="优先补极限与连续",
                reason="该知识点近 7 天正确率最低",
                action="重做第一章测验并整理错题",
                priority="high",
            ),
            AdviceSuggestion(
                title="保持每日任务节奏",
                reason="完成率 78% 略低于目标",
                action="把每日目标调到 60 分钟",
                priority="medium",
            ),
        ],
        weak_points=[{"knowledge": "模型编造的"}],
        next_7_days=[{"date": "2000-01-01", "minutes": 999}],
    )


@pytest.fixture
def stub_models(monkeypatch):
    """把模型调用换成假实现（真实链路其余部分不变）。"""

    async def fake_invoke(scene: str, *, user_id, db, user_message: str):
        if scene == "summary":
            return fake_summary(), FAKE_USAGE
        if scene == "quiz":
            # 从提示里解析需要几道题、什么题型（保持与真实调用一致的形状）
            count = 2
            types = ["single"]
            if "判断题" in user_message:
                types = ["judge"]
            return fake_quiz(count=count, types=types), FAKE_USAGE
        if scene == "advice":
            return fake_advice(), FAKE_USAGE
        raise AssertionError(f"未打桩的场景: {scene}")

    monkeypatch.setattr(ai_common, "invoke_structured", fake_invoke)
    return fake_invoke


@pytest.fixture
async def parsed_material(db_session: AsyncSession, test_user) -> Material:
    return await make_material(
        db_session, test_user, title="高数第一章", text="极限的定义与性质。" * 20
    )


# --------------------------------------------------------------------- 总结


async def test_generate_summary_persists_generation_and_usage(
    db_client, db_session: AsyncSession, auth_headers, test_user, parsed_material, stub_models
):
    resp = await db_client.post(
        SUMMARIES_URL,
        json={"material_id": str(parsed_material.id), "style": "outline"},
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "direct"
    assert body["key_points"] == ["ε-δ 定义", "左右极限"]
    assert body["prompt_tokens"] == 120
    assert body["segments"] == 1

    generation = await db_session.get(AiGeneration, uuid.UUID(body["id"]))
    assert generation.scene == "summary"
    assert generation.ref_id == parsed_material.id
    assert generation.output_data["mode"] == "direct"

    # 只取「刚刚这次」写入的用量行：本地开发库里可能还有真实模型的历史记录
    usage_row = await db_session.scalar(
        select(AiUsage)
        .where(AiUsage.scene == "summary", AiUsage.user_id == test_user.id)
        .order_by(AiUsage.created_at.desc())
        .limit(1)
    )
    assert usage_row.prompt_tokens == 120
    assert usage_row.total_tokens == 200
    assert usage_row.steps == 2


async def test_summary_list_hides_body(db_client, auth_headers, parsed_material, stub_models):
    await db_client.post(
        SUMMARIES_URL,
        json={"material_id": str(parsed_material.id)},
        headers=auth_headers,
    )

    listing = await db_client.get(SUMMARIES_URL, headers=auth_headers)

    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert "summary_md" not in item
    assert item["key_points"]


async def test_summary_requires_parsed_material(db_client, db_session, auth_headers, test_user):
    pending = await make_material(db_session, test_user, parse_status="pending")

    resp = await db_client.post(
        SUMMARIES_URL, json={"material_id": str(pending.id)}, headers=auth_headers
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "MAT_001"


async def test_summary_rejects_scanned_material(db_client, db_session, auth_headers, test_user):
    scanned = await make_material(db_session, test_user, parse_status="unsupported")

    resp = await db_client.post(
        SUMMARIES_URL, json={"material_id": str(scanned.id)}, headers=auth_headers
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "MAT_004"


async def test_summary_of_other_users_material_is_404(
    db_client, db_session: AsyncSession, test_user, auth_headers, parsed_material, stub_models
):
    from app.schemas.user import UserCreate
    from app.services import user_service

    other = await user_service.create_user(
        db_session,
        UserCreate(username="ai_other", email="ai_other@example.com", password=TEST_PASSWORD),
    )
    other_material = await make_material(db_session, other, title="别人的资料")

    resp = await db_client.post(
        SUMMARIES_URL, json={"material_id": str(other_material.id)}, headers=auth_headers
    )

    assert resp.status_code == 404


# --------------------------------------------------------------------- 时未配置 Key


async def test_ai_endpoints_return_503_without_api_key(
    db_client, auth_headers, parsed_material, monkeypatch
):
    """没配 LLM_API_KEY 时给「功能未开启」，而不是 500。"""
    monkeypatch.setattr(settings, "llm_api_key", "")

    resp = await db_client.post(
        SUMMARIES_URL, json={"material_id": str(parsed_material.id)}, headers=auth_headers
    )

    assert resp.status_code == 503
    assert resp.json()["code"] == "SYS_503"


async def test_quota_exceeded_returns_429(
    db_client, auth_headers, parsed_material, stub_models, monkeypatch
):
    monkeypatch.setattr(settings, "ai_daily_quota", 0)

    resp = await db_client.post(
        SUMMARIES_URL, json={"material_id": str(parsed_material.id)}, headers=auth_headers
    )

    assert resp.status_code == 429
    assert resp.json()["code"] == "AI_004"


# --------------------------------------------------------------------- 测试题


async def test_generate_quiz_and_submit_attempt(
    db_client, db_session: AsyncSession, auth_headers, parsed_material, stub_models
):
    created = await db_client.post(
        GENERATE_QUIZ_URL,
        json={
            "material_id": str(parsed_material.id),
            "count": 2,
            "types": ["single"],
            "difficulty": "medium",
        },
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    quiz = created.json()
    assert quiz["question_count"] == 2
    assert quiz["questions"][0]["answer"] == ["B 选项"]

    # 列表不含题目（防答案泄露）
    listing = await db_client.get(QUIZZES_URL, headers=auth_headers)
    assert "questions" not in listing.json()["items"][0]

    # 答题页用 with_answer=false
    masked = await db_client.get(f"{QUIZZES_URL}/{quiz['id']}?with_answer=false",
        headers=auth_headers)
    assert masked.json()["questions"][0]["answer"] is None
    assert masked.json()["questions"][0]["explanation"] is None

    # 一题对一题错 → 50 分
    attempt = await db_client.post(
        f"{QUIZZES_URL}/{quiz['id']}/attempts",
        json={
            "answers": [{"no": 1, "answer": ["B 选项"]}, {"no": 2, "answer": ["A 选项"]}],
            "duration_seconds": 90,
        },
        headers=auth_headers,
    )

    assert attempt.status_code == 201, attempt.text
    body = attempt.json()
    assert body["score"] == 50.0
    assert body["correct_count"] == 1
    assert len(body["details"]) == 2
    assert body["details"][0]["is_correct"] is True
    assert body["details"][1]["explanation"] is not None

    attempts = await db_client.get(f"{QUIZZES_URL}/{quiz['id']}/attempts", headers=auth_headers)
    assert attempts.json()["total"] == 1


async def test_judge_quiz_generation(
    db_client, auth_headers, parsed_material, stub_models
):
    created = await db_client.post(
        GENERATE_QUIZ_URL,
        json={"material_id": str(parsed_material.id), "count": 2, "types": ["judge"]},
        headers=auth_headers,
    )

    assert created.status_code == 201
    questions = created.json()["questions"]
    assert all(question["type"] == "judge" for question in questions)
    # 判断题的选项被强制为标准选项
    assert questions[0]["options"] == ["正确", "错误"]


# --------------------------------------------------------------------- 学习建议


async def test_generate_advice_overrides_model_data(
    db_client, auth_headers, stub_models, test_user
):
    resp = await db_client.post(ADVICE_URL + "/generate", json={"days": 7, "focus": "review"},
        headers=auth_headers)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["suggestions"]) == 2
    # 模型编造的 next_7_days 被后端计算的结果覆盖
    assert body["next_7_days"][0]["date"] != "2000-01-01"
    assert body["next_7_days"][0]["minutes"] <= test_user.daily_target_minutes * 1.5
    # weak_points 也来自后端（此时样本不足 → 空）
    assert body["weak_points"] == []

    latest = await db_client.get(ADVICE_URL, headers=auth_headers)
    assert latest.json()["advice"]["id"] == body["id"]
    assert latest.json()["stale"] is False


# --------------------------------------------------------------------- 用量


async def test_usage_endpoint_after_calls(
    db_client, auth_headers, parsed_material, stub_models
):
    await db_client.post(
        SUMMARIES_URL, json={"material_id": str(parsed_material.id)}, headers=auth_headers
    )

    resp = await db_client.get(f"{USAGE_URL}?days=7", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["today_calls"] >= 1
    assert body["total_tokens"] >= 200
    assert body["daily_quota"] == settings.ai_daily_quota
    assert body["items"]
    assert body["items"][0]["calls"] >= 1


# --------------------------------------------------------------------- 问答（含 SSE）


async def test_chat_session_lifecycle_and_ask(
    db_client, auth_headers, monkeypatch, parsed_material
):
    async def fake_invoke_text(scene, *, user_id, db, messages):
        assert scene == "qa"
        return (
            "极限的定义是……（依据资料）",
            [{"name": "search_material", "args": {"keyword": "极限"}}],
            FAKE_USAGE,
        )

    monkeypatch.setattr(chat_service, "invoke_text", fake_invoke_text)

    session = await db_client.post(SESSIONS_URL, json={"title": None}, headers=auth_headers)
    assert session.status_code == 201
    session_id = session.json()["id"]

    answer = await db_client.post(
        f"{SESSIONS_URL}/{session_id}/messages",
        json={"content": "第一章的极限定义是什么？"},
        headers=auth_headers,
    )

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert "依据资料" in body["content"]
    assert body["tool_calls"][0]["name"] == "search_material"
    assert body["completion_tokens"] == 80

    messages = await db_client.get(f"{SESSIONS_URL}/{session_id}/messages", headers=auth_headers)
    assert messages.json()["total"] == 2  # 用户 + 助手
    assert [item["role"] for item in messages.json()["items"]] == ["user", "assistant"]

    # 首问后会话标题被更新
    sessions = await db_client.get(SESSIONS_URL, headers=auth_headers)
    assert sessions.json()["items"][0]["title"] != "新会话"

    deleted = await db_client.delete(f"{SESSIONS_URL}/{session_id}", headers=auth_headers)
    assert deleted.status_code == 204
    gone = await db_client.get(f"{SESSIONS_URL}/{session_id}/messages", headers=auth_headers)
    assert gone.status_code == 404


async def test_chat_stream_emits_sse_events(
    db_client, auth_headers, monkeypatch
):
    async def fake_stream(scene, *, user_id, db, messages):
        yield {"event": "delta", "data": {"text": "极限的"}}
        yield {"event": "delta", "data": {"text": "定义是……"}}
        yield {
            "event": "done",
            "data": {
                "text": "极限的定义是……",
                "tool_calls": [],
                "usage": AgentUsage(prompt_tokens=10, completion_tokens=20, steps=1,
                    latency_ms=100),
            },
        }

    monkeypatch.setattr(chat_service, "stream_text", fake_stream)

    session = await db_client.post(SESSIONS_URL, json={}, headers=auth_headers)
    session_id = session.json()["id"]

    async with db_client.stream(
        "POST",
        f"{SESSIONS_URL}/{session_id}/messages/stream",
        json={"content": "什么是极限？"},
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join([chunk async for chunk in response.aiter_text()])

    assert "event: meta" in raw
    assert "event: delta" in raw
    assert "event: done" in raw
    assert "极限的" in raw


async def test_chat_is_isolated_between_users(
    db_client, db_session: AsyncSession, test_user, auth_headers
):
    from app.schemas.user import UserCreate
    from app.services import user_service

    session = await db_client.post(SESSIONS_URL, json={}, headers=auth_headers)
    session_id = session.json()["id"]

    await user_service.create_user(
        db_session,
        UserCreate(username="chat_other", email="chat_other@example.com", password=TEST_PASSWORD),
    )
    intruder = await login(db_client, "chat_other", TEST_PASSWORD)

    assert (await db_client.get(SESSIONS_URL, headers=intruder)).json()["total"] == 0
    assert (
        await db_client.post(
            f"{SESSIONS_URL}/{session_id}/messages", json={"content": "偷看"}, headers=intruder
        )
    ).status_code == 404
    assert (
        await db_client.delete(f"{SESSIONS_URL}/{session_id}", headers=intruder)
    ).status_code == 404
