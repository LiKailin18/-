"""统计与个性化推荐接口（契约：docs/api.md §12）。

- §12.1 学习数据统计（功能 11）：薄薄一层，口径全在 `stats_service`
- §12.2 个性化学习推荐（功能 10 的规则层）：`recommend_service`，不调用大模型

本文件只做参数校验与出参装配，不写聚合逻辑（CLAUDE.md §5.1）。
"""

from datetime import date, timedelta

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import BadRequest
from app.core.openapi import ERR_401, ERR_403
from app.schemas.stats import (
    RecommendationItem,
    RecommendationsOut,
    StatsDailyItem,
    StatsDailyOut,
    StatsOverviewOut,
    StatsSubjectsOut,
    SubjectStatItem,
    WeakPointItem,
    WeakPointsOut,
)
from app.services import recommend_service, stats_service
from app.utils.time import today_local

router = APIRouter(
    tags=["统计与推荐"],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
    },
)

MAX_RANGE_DAYS = 365
DEFAULT_RANGE_DAYS = 30


def _resolve_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """默认近 30 天；区间上限 365 天（契约 §12.1 的 daily / subjects 共用）。"""
    end = date_to or today_local()
    start = date_from or end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if start > end:
        raise BadRequest("date_from 不能晚于 date_to")
    if (end - start).days >= MAX_RANGE_DAYS:
        raise BadRequest(f"统计区间不能超过 {MAX_RANGE_DAYS} 天")
    return start, end


@router.get("/stats/overview", summary="学习概览", response_model=StatsOverviewOut)
async def stats_overview(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(default=7, ge=1, le=365, description="统计窗口（天）"),
) -> StatsOverviewOut:
    data = await stats_service.overview(db, user_id=current_user.id, days=days)
    return StatsOverviewOut.model_validate(data)


@router.get("/stats/daily", summary="每日趋势", response_model=StatsDailyOut)
async def stats_daily(
    current_user: CurrentUser,
    db: DbSession,
    date_from: date | None = Query(default=None, description="起始日期（含），默认近 30 天"),
    date_to: date | None = Query(default=None, description="结束日期（含），默认今天"),
) -> StatsDailyOut:
    start, end = _resolve_range(date_from, date_to)
    rows = await stats_service.daily(db, user_id=current_user.id, date_from=start, date_to=end)
    return StatsDailyOut(items=[StatsDailyItem.model_validate(row) for row in rows])


@router.get("/stats/subjects", summary="科目分布", response_model=StatsSubjectsOut)
async def stats_subjects(
    current_user: CurrentUser,
    db: DbSession,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> StatsSubjectsOut:
    start, end = _resolve_range(date_from, date_to)
    rows = await stats_service.subject_minutes(
        db, user_id=current_user.id, date_from=start, date_to=end
    )
    return StatsSubjectsOut(items=[SubjectStatItem.model_validate(row) for row in rows])


@router.get("/stats/weak-points", summary="薄弱知识点", response_model=WeakPointsOut)
async def stats_weak_points(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=5, ge=1, le=10),
) -> WeakPointsOut:
    rows = await stats_service.weak_points(
        db, user_id=current_user.id, days=days, limit=limit
    )
    return WeakPointsOut(items=[WeakPointItem.model_validate(row) for row in rows])


@router.get("/recommendations", summary="个性化学习推荐（规则）", response_model=RecommendationsOut)
async def recommendations(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=5, ge=1, le=10),
) -> RecommendationsOut:
    items = await recommend_service.build(
        db,
        user_id=current_user.id,
        daily_target_minutes=current_user.daily_target_minutes,
        limit=limit,
    )
    return RecommendationsOut(
        generated_at=recommend_service.generated_at(),
        items=[RecommendationItem.model_validate(item) for item in items],
    )
