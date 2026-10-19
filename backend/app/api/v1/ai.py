"""AI 接口（契约：docs/api.md §10、§11、§14）—— 功能 7 / 8 / 10。"""

import json
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.ai import usage as usage_module
from app.core.deps import CurrentUser, DbSession, PageParams, get_ai_enabled
from app.core.openapi import (
    ERR_400,
    ERR_401,
    ERR_403,
    ERR_404,
    ERR_429,
    ERR_502,
    ERR_503,
    ERR_504,
)
from app.schemas.ai import (
    AdviceBrief,
    AdviceGenerateIn,
    AdviceLatestOut,
    AdviceOut,
    AdviceSuggestionOut,
    ChatAnswerOut,
    ChatAskIn,
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionOut,
    SummaryBrief,
    SummaryCreate,
    SummaryOut,
    UsageDailyItem,
    UsageOut,
)
from app.schemas.common import Page
from app.services import advice_service, chat_service, summary_service
from app.utils.time import app_tz, today_local

router = APIRouter(
    prefix="/ai",
    tags=["AI 能力"],
    # 总开关：管理员关掉 ai.enabled 后整组接口 503（功能 13.5）
    dependencies=[Depends(get_ai_enabled)],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
        status.HTTP_429_TOO_MANY_REQUESTS: ERR_429,
        status.HTTP_503_SERVICE_UNAVAILABLE: ERR_503,
        status.HTTP_504_GATEWAY_TIMEOUT: ERR_504,
    },
)

AI_ERRORS = {
    status.HTTP_400_BAD_REQUEST: ERR_400,
    status.HTTP_502_BAD_GATEWAY: ERR_502,
}


# --------------------------------------------------------------------- 总结


def _summary_out(row) -> SummaryOut:
    data = row.output_data or {}
    return SummaryOut(
        id=row.id,
        material_id=row.ref_id,
        style=(row.input_params or {}).get("style", "outline"),
        mode=data.get("mode", "direct"),
        summary_md=row.output_md or "",
        key_points=data.get("key_points", []),
        char_count=data.get("char_count", 0),
        segments=data.get("segments", 1),
        model=row.model,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
    )


@router.post(
    "/summaries",
    summary="生成资料总结",
    status_code=status.HTTP_201_CREATED,
    response_model=SummaryOut,
    responses=AI_ERRORS,
)
async def create_summary(
    payload: SummaryCreate, current_user: CurrentUser, db: DbSession
) -> SummaryOut:
    row, _retries = await summary_service.generate(db, user=current_user, data=payload)
    return _summary_out(row)


@router.get("/summaries", summary="资料总结列表", response_model=Page[SummaryBrief])
async def list_summaries(
    current_user: CurrentUser,
    db: DbSession,
    page: PageParams,
    material_id: uuid.UUID | None = None,
) -> Page[SummaryBrief]:
    rows, total = await summary_service.list_summaries(
        db, user_id=current_user.id, offset=page.offset, limit=page.size, material_id=material_id
    )
    items = [
        SummaryBrief(
            id=row.id,
            material_id=row.ref_id,
            style=(row.input_params or {}).get("style", "outline"),
            mode=(row.output_data or {}).get("mode", "direct"),
            key_points=[point[:80] for point in (row.output_data or {}).get("key_points", [])],
            char_count=(row.output_data or {}).get("char_count", 0),
            created_at=row.created_at,
        )
        for row in rows
    ]
    return Page[SummaryBrief](items=items, total=total, page=page.page, size=page.size)


@router.get("/summaries/{summary_id}", summary="资料总结详情", response_model=SummaryOut)
async def get_summary(
    summary_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> SummaryOut:
    row = await summary_service.get_owned(db, current_user.id, summary_id)
    return _summary_out(row)


# --------------------------------------------------------------------- 学习建议


def _advice_out(row, *, stale: bool = False) -> AdviceOut:
    data = row.output_data or {}
    return AdviceOut(
        id=row.id,
        period_days=data.get("period_days", 7),
        focus=data.get("focus", "review"),
        summary=data.get("summary", row.output_md or ""),
        suggestions=[AdviceSuggestionOut(**item) for item in data.get("suggestions", [])],
        weak_points=data.get("weak_points", []),
        next_7_days=data.get("next_7_days", []),
        stale=stale,
        model=row.model,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
    )


@router.post(
    "/advice/generate",
    summary="生成学习建议",
    status_code=status.HTTP_201_CREATED,
    response_model=AdviceOut,
    responses=AI_ERRORS,
)
async def generate_advice(
    payload: AdviceGenerateIn, current_user: CurrentUser, db: DbSession
) -> AdviceOut:
    row, _retries = await advice_service.generate(db, user=current_user, data=payload)
    return _advice_out(row)


@router.get("/advice", summary="最近一次学习建议", response_model=AdviceLatestOut)
async def latest_advice(
    current_user: CurrentUser,
    db: DbSession,
    stale_days: int = Query(default=1, ge=0, le=90),
) -> AdviceLatestOut:
    row = await advice_service.latest(db, current_user.id)
    if row is None:
        return AdviceLatestOut(advice=None, stale=False)

    # 按业务时区判断「几天前的建议」，避免 UTC 与东八区差一天
    age_days = (today_local() - row.created_at.astimezone(app_tz()).date()).days
    return AdviceLatestOut(advice=_advice_out(row), stale=age_days > stale_days)


@router.get("/advice/history", summary="学习建议历史", response_model=Page[AdviceBrief])
async def advice_history(
    current_user: CurrentUser, db: DbSession, page: PageParams
) -> Page[AdviceBrief]:
    rows, total = await advice_service.history(
        db, user_id=current_user.id, offset=page.offset, limit=page.size
    )
    items = [
        AdviceBrief(
            id=row.id,
            period_days=(row.output_data or {}).get("period_days", 7),
            focus=(row.output_data or {}).get("focus", "review"),
            summary=(row.output_data or {}).get("summary", row.output_md or "")[:200],
            created_at=row.created_at,
        )
        for row in rows
    ]
    return Page[AdviceBrief](items=items, total=total, page=page.page, size=page.size)


# --------------------------------------------------------------------- 会话与问答


@router.post(
    "/chat-sessions",
    summary="新建问答会话",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatSessionOut,
)
async def create_chat_session(
    payload: ChatSessionCreate, current_user: CurrentUser, db: DbSession
) -> ChatSessionOut:
    session = await chat_service.create_session(db, user=current_user, data=payload)
    return ChatSessionOut.model_validate(session)


@router.get("/chat-sessions", summary="会话列表", response_model=Page[ChatSessionOut])
async def list_chat_sessions(
    current_user: CurrentUser, db: DbSession, page: PageParams
) -> Page[ChatSessionOut]:
    rows, total = await chat_service.list_sessions(
        db, user_id=current_user.id, offset=page.offset, limit=page.size
    )
    return Page[ChatSessionOut](
        items=[ChatSessionOut.model_validate(row) for row in rows],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.get(
    "/chat-sessions/{session_id}/messages",
    summary="会话历史消息",
    response_model=Page[ChatMessageOut],
)
async def list_chat_messages(
    session_id: uuid.UUID, current_user: CurrentUser, db: DbSession, page: PageParams
) -> Page[ChatMessageOut]:
    session = await chat_service.get_owned(db, current_user.id, session_id)
    rows, total = await chat_service.list_messages(
        db, session_id=session.id, offset=page.offset, limit=page.size
    )
    return Page[ChatMessageOut](
        items=[ChatMessageOut.model_validate(row) for row in rows],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.delete(
    "/chat-sessions/{session_id}", summary="删除会话", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_chat_session(
    session_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> None:
    session = await chat_service.get_owned(db, current_user.id, session_id)
    await chat_service.delete_session(db, session)


@router.post(
    "/chat-sessions/{session_id}/messages",
    summary="提问（非流式）",
    response_model=ChatAnswerOut,
    responses=AI_ERRORS,
)
async def ask_question(
    session_id: uuid.UUID, payload: ChatAskIn, current_user: CurrentUser, db: DbSession
) -> ChatAnswerOut:
    session = await chat_service.get_owned(db, current_user.id, session_id)
    return await chat_service.ask(db, session=session, data=payload)


@router.post(
    "/chat-sessions/{session_id}/messages/stream",
    summary="提问（流式 SSE）",
    responses=AI_ERRORS,
)
async def ask_question_stream(
    session_id: uuid.UUID,
    payload: ChatAskIn,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> EventSourceResponse:
    """SSE 事件协议见 docs/api.md §13；每 15s 一个心跳防代理断连。"""
    session = await chat_service.get_owned(db, current_user.id, session_id)

    async def event_generator():
        async for item in chat_service.ask_stream(db, session=session, data=payload):
            if await request.is_disconnected():
                break
            yield {
                "event": item["event"],
                "data": json.dumps(item["data"], ensure_ascii=False),
            }

    return EventSourceResponse(event_generator(), ping=15)


# --------------------------------------------------------------------- 用量


@router.get("/usage", summary="AI 调用用量", response_model=UsageOut)
async def get_usage(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(default=7, ge=1, le=90),
) -> UsageOut:
    summary = await usage_module.usage_summary(db, user_id=current_user.id, days=days)
    items = await usage_module.usage_daily(db, user_id=current_user.id, days=days)
    return UsageOut(**summary, items=[UsageDailyItem(**item) for item in items])
