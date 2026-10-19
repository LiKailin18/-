"""管理端 AI 调用明细（功能 13.4；契约：docs/api.md §16.4）。"""

import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.core.deps import CurrentAdmin, DbSession, PageParams
from app.schemas.admin import AiUsageItemOut, AiUsagePage
from app.services import admin_stats_service

router = APIRouter(prefix="/ai-usage", tags=["管理端 · AI 用量"])


@router.get("", summary="AI 调用明细", response_model=AiUsagePage)
async def list_ai_usage(
    _admin: CurrentAdmin,
    db: DbSession,
    page: PageParams,
    user_id: uuid.UUID | None = None,
    scene: str | None = Query(default=None, description="qa / summary / quiz / advice"),
    ok: bool | None = Query(default=None, description="只看成功 / 失败"),
    date_from: date | None = None,
    date_to: date | None = None,
) -> AiUsagePage:
    items, total = await admin_stats_service.list_ai_usage(
        db,
        offset=page.offset,
        limit=page.size,
        user_id=user_id,
        scene=scene,
        ok=ok,
        date_from=date_from,
        date_to=date_to,
    )
    return AiUsagePage(
        items=[AiUsageItemOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )
