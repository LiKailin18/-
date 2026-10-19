"""AI 问答（功能 7）：会话、消息与两种调用方式（流式 / 非流式）。

会话历史**存在自己的表里**，不用 checkpointer（CLAUDE.md §3.6）：
数据归属清晰、可按用户/资料过滤、便于统计 token 与展示历史。
"""

import uuid
from collections.abc import AsyncIterator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import usage as usage_module
from app.ai.runtime import AgentUsage, invoke_text, stream_text
from app.core.config import settings
from app.core.exceptions import AiTimeout, AiUpstreamError, NotFound
from app.models import AppUser, ChatMessage, ChatSession, Material, utcnow
from app.schemas.ai import ChatAnswerOut, ChatAskIn, ChatSessionCreate
from app.utils.text import make_excerpt

# 传给模型的最近轮数（太长的历史会挤占资料上下文）
HISTORY_TURNS = 8


async def create_session(
    db: AsyncSession, *, user: AppUser, data: ChatSessionCreate
) -> ChatSession:
    if data.material_id is not None:
        owned = await db.scalar(
            select(Material.id).where(
                Material.id == data.material_id,
                Material.user_id == user.id,
                Material.deleted_at.is_(None),
            )
        )
        if owned is None:
            raise NotFound("资料不存在")

    session = ChatSession(
        user_id=user.id,
        material_id=data.material_id,
        title=(data.title or "新会话")[:200],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession, *, user_id: uuid.UUID, offset: int, limit: int
) -> tuple[list[ChatSession], int]:
    conditions = [ChatSession.user_id == user_id, ChatSession.deleted_at.is_(None)]
    total = await db.scalar(select(func.count()).select_from(ChatSession).where(*conditions))
    rows = (
        await db.execute(
            select(ChatSession)
            .where(*conditions)
            .order_by(ChatSession.last_message_at.desc().nullslast(), ChatSession.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total or 0)


async def get_owned(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession:
    session = await db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.deleted_at.is_(None),
        )
    )
    if session is None:
        raise NotFound("会话不存在")
    return session


async def list_messages(
    db: AsyncSession, *, session_id: uuid.UUID, offset: int, limit: int
) -> tuple[list[ChatMessage], int]:
    conditions = [ChatMessage.session_id == session_id, ChatMessage.deleted_at.is_(None)]
    total = await db.scalar(select(func.count()).select_from(ChatMessage).where(*conditions))
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(*conditions)
            .order_by(ChatMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total or 0)


async def delete_session(db: AsyncSession, session: ChatSession) -> None:
    moment = utcnow()
    message_rows = (
        await db.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session.id, ChatMessage.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    for message in message_rows:
        message.deleted_at = moment
    session.deleted_at = moment
    session.updated_at = moment
    await db.commit()


async def _history_messages(
    db: AsyncSession, session: ChatSession, *, question: str
) -> list[dict]:
    """把最近若干轮对话拼成 agent 需要的 messages。"""
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id, ChatMessage.deleted_at.is_(None))
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_TURNS * 2)
        )
    ).scalars().all()

    messages = [
        {"role": row.role, "content": row.content} for row in reversed(list(rows))
    ]

    hint = ""
    if session.material_id:
        material = await db.get(Material, session.material_id)
        if material is not None:
            hint = f"\n（本次会话限定资料：{material.title}，material_id={material.id}）"

    messages.append({"role": "user", "content": f"{question}{hint}"})
    return messages


async def _append_message(
    db: AsyncSession,
    *,
    session: ChatSession,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int | None = None,
) -> ChatMessage:
    message = ChatMessage(
        session_id=session.id,
        user_id=session.user_id,
        role=role,
        content=content,
        tool_calls=tool_calls or None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )
    db.add(message)

    session.message_count += 1
    session.last_message_at = utcnow()
    session.updated_at = utcnow()
    # 标题取首问前 20 字（不额外调用模型）
    if session.message_count <= 2 and session.title == "新会话":
        session.title = make_excerpt(content, limit=20) or "新会话"

    await db.commit()
    await db.refresh(message)
    return message


async def ask(db: AsyncSession, *, session: ChatSession, data: ChatAskIn) -> ChatAnswerOut:
    """非流式问答（前端降级开关与自动化测试都用它）。"""
    await usage_module.ensure_quota(db, user_id=session.user_id)
    await _append_message(db, session=session, role="user", content=data.content)

    messages = await _history_messages(db, session, question=data.content)
    answer, tool_calls, usage = await invoke_text(
        "qa", user_id=session.user_id, db=db, messages=messages
    )

    message = await _append_message(
        db,
        session=session,
        role="assistant",
        content=answer or "（模型没有返回内容）",
        tool_calls=tool_calls,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=usage.latency_ms,
    )
    await usage_module.record_usage(
        db, user_id=session.user_id, scene="qa", model=settings.llm_model, usage=usage
    )

    return ChatAnswerOut(
        id=message.id,
        content=message.content,
        tool_calls=tool_calls,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=usage.latency_ms,
        created_at=message.created_at,
    )


async def ask_stream(
    db: AsyncSession, *, session: ChatSession, data: ChatAskIn
) -> AsyncIterator[dict]:
    """流式问答：逐个 yield SSE 事件（契约 §13）。

    事件：meta → tool* → delta* → done；失败发 error。
    消息落库在 done 事件之前完成，前端收到 done 后应让消息列表查询失效。
    """
    await usage_module.ensure_quota(db, user_id=session.user_id)
    user_message = await _append_message(
        db, session=session, role="user", content=data.content
    )

    yield {
        "event": "meta",
        "data": {
            "session_id": str(session.id),
            "message_id": str(user_message.id),
            "model": settings.llm_model,
        },
    }

    messages = await _history_messages(db, session, question=data.content)
    usage: AgentUsage | None = None
    collected: list[str] = []
    tool_calls: list[dict] = []

    try:
        async for event in stream_text("qa", user_id=session.user_id, db=db, messages=messages):
            if event["event"] == "done":
                usage = event["data"]["usage"]
                collected = [event["data"]["text"]]
                tool_calls = event["data"]["tool_calls"]
                continue
            if event["event"] == "delta":
                collected.append(event["data"]["text"])
            yield event
    except (AiTimeout, AiUpstreamError) as exc:
        # 失败也要落库（ok=false），并把 error 事件发出去，不能让连接静默中断
        await usage_module.record_usage(
            db,
            user_id=session.user_id,
            scene="qa",
            model=settings.llm_model,
            usage=AgentUsage(),
            ok=False,
            error_code=exc.code,
        )
        yield {"event": "error", "data": {"code": exc.code, "message": exc.message}}
        return

    answer = "".join(chunk for chunk in collected if chunk)
    assistant = await _append_message(
        db,
        session=session,
        role="assistant",
        content=answer or "（模型没有返回内容）",
        tool_calls=tool_calls,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        latency_ms=usage.latency_ms if usage else None,
    )
    if usage:
        await usage_module.record_usage(
            db, user_id=session.user_id, scene="qa", model=settings.llm_model, usage=usage
        )

    yield {
        "event": "done",
        "data": {
            "message_id": str(assistant.id),
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
            "latency_ms": usage.latency_ms if usage else 0,
            "finish_reason": "stop",
        },
    }
