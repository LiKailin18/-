"""学习数据相关工具（契约：docs/agent-tools.md §3.4、§3.6）。"""

import uuid

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import stats_service


def make_get_study_stats(user_id: uuid.UUID, db: AsyncSession):
    """返回聚合后的学习统计（绝不是原始流水）。"""

    @tool
    async def get_study_stats(days: int = 7) -> dict:
        """Return aggregated study statistics for the last N days.

        Contains total study minutes, active days, streak, task completion rate
        and quiz accuracy. Returns aggregates only - never raw records.
        """
        safe_days = max(1, min(days, 90))
        data = await stats_service.overview(db, user_id=user_id, days=safe_days)
        return {"ok": True, "data": data, "meta": {"count": 1, "truncated": False}}

    return get_study_stats


def make_get_weak_points(user_id: uuid.UUID, db: AsyncSession):
    """薄弱知识点：按正确率升序，样本太少的会被过滤。"""

    @tool
    async def get_weak_points(days: int = 30, limit: int = 5) -> dict:
        """Return the user's weakest knowledge points ordered by quiz accuracy.

        Only knowledge points with at least 3 attempts are included, so the
        result is statistically meaningful.
        """
        safe_days = max(1, min(days, 180))
        safe_limit = max(1, min(limit, 10))
        points = await stats_service.weak_points(
            db, user_id=user_id, days=safe_days, limit=safe_limit
        )
        return {
            "ok": True,
            "data": {"weak_points": points},
            "meta": {"count": len(points), "truncated": False},
        }

    return get_weak_points
