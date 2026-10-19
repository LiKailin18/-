"""管理端仪表盘（功能 13.1；契约：docs/api.md §16.1）。"""

from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.core.deps import CurrentAdmin, DbSession
from app.schemas.admin import (
    AdminAiDailyOut,
    AdminAiStatsOut,
    AdminDailyItemOut,
    AdminDailyOut,
    AdminOverviewOut,
    SceneStatOut,
    TopUserOut,
)
from app.services import admin_stats_service
from app.utils.time import today_local

router = APIRouter(prefix="/stats", tags=["管理端 · 仪表盘"])

MAX_RANGE_DAYS = 365


@router.get("/overview", summary="全站概览", response_model=AdminOverviewOut)
async def admin_overview(
    _admin: CurrentAdmin,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=365, description="统计窗口（天）"),
) -> AdminOverviewOut:
    data = await admin_stats_service.overview(db, days=days)
    return AdminOverviewOut.model_validate(data)


@router.get("/daily", summary="全站每日趋势", response_model=AdminDailyOut)
async def admin_daily(
    _admin: CurrentAdmin,
    db: DbSession,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> AdminDailyOut:
    end = date_to or today_local()
    start = date_from or (end - timedelta(days=29))
    rows = await admin_stats_service.daily(db, date_from=start, date_to=end)
    return AdminDailyOut(items=[AdminDailyItemOut.model_validate(row) for row in rows])


@router.get("/ai", summary="AI 用量分布", response_model=AdminAiStatsOut)
async def admin_ai_stats(
    _admin: CurrentAdmin,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> AdminAiStatsOut:
    data = await admin_stats_service.ai_breakdown(db, days=days)
    return AdminAiStatsOut(
        by_scene=[SceneStatOut.model_validate(row) for row in data["by_scene"]],
        top_users=[TopUserOut.model_validate(row) for row in data["top_users"]],
        daily=[AdminAiDailyOut.model_validate(row) for row in data["daily"]],
    )
