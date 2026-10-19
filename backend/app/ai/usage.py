"""用量与配额（契约：docs/agent-tools.md §8）。

- 一次请求写一行 ai_usage；token 为 agent 多轮累加值
- 配额按**业务时区**的当日计数（不是 UTC 日）
"""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime import AgentUsage
from app.core.exceptions import AiQuotaExceeded, FeatureDisabled
from app.models import AiUsage
from app.utils.time import app_tz

SCENES = ("qa", "summary", "quiz", "advice")


async def ensure_quota(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    """AI 生成前的统一闸门：先看总开关，再看当日配额。

    四个场景（qa / summary / quiz / advice）都从这里进，所以「ai.enabled=false 后
    生成类接口一律 503」只在这一处实现即可；历史列表、答卷判分不经过这里，
    不受影响（它们不消耗模型调用）。
    """
    from app.services import setting_service

    if not await setting_service.is_enabled(db, "ai.enabled"):
        raise FeatureDisabled("AI 功能已暂停，请联系管理员")

    quota = await setting_service.get_int(db, "ai.daily_quota")

    used = await db.scalar(
        select(func.count())
        .select_from(AiUsage)
        .where(
            AiUsage.user_id == user_id,
            func.date(AiUsage.created_at.op("AT TIME ZONE")(str(app_tz())))
            == func.current_date(),
        )
    )
    used_count = int(used or 0)
    if used_count >= quota:
        raise AiQuotaExceeded
    return used_count


async def record_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    scene: str,
    model: str,
    usage: AgentUsage,
    ok: bool = True,
    error_code: str | None = None,
) -> AiUsage:
    """写入一条调用流水（agent 多轮 token 已由 runtime 累加）。"""
    row = AiUsage(
        user_id=user_id,
        scene=scene,
        model=model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        steps=max(usage.steps, 1),
        latency_ms=usage.latency_ms or None,
        ok=ok,
        error_code=error_code,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def usage_summary(db: AsyncSession, *, user_id: uuid.UUID, days: int = 7) -> dict:
    """近 N 天用量汇总（给 GET /ai/usage）。"""
    from datetime import timedelta

    from app.services import setting_service
    from app.utils.time import today_local

    quota = await setting_service.get_int(db, "ai.daily_quota")

    end = today_local()
    start = end - timedelta(days=days - 1)

    row = (
        await db.execute(
            select(
                func.count().label("calls"),
                func.coalesce(func.sum(AiUsage.prompt_tokens), 0).label("prompt"),
                func.coalesce(func.sum(AiUsage.completion_tokens), 0).label("completion"),
                func.count().filter(AiUsage.ok.is_(True)).label("ok_calls"),
            ).where(
                AiUsage.user_id == user_id,
                func.date(AiUsage.created_at.op("AT TIME ZONE")(str(app_tz()))).between(start, end),
            )
        )
    ).one()

    today_calls = await db.scalar(
        select(func.count())
        .select_from(AiUsage)
        .where(
            AiUsage.user_id == user_id,
            func.date(AiUsage.created_at.op("AT TIME ZONE")(str(app_tz()))) == end,
        )
    )

    calls = int(row.calls or 0)
    return {
        "days": days,
        "today_calls": int(today_calls or 0),
        "daily_quota": quota,
        "prompt_tokens": int(row.prompt or 0),
        "completion_tokens": int(row.completion or 0),
        "total_tokens": int(row.prompt or 0) + int(row.completion or 0),
        "success_rate": round(int(row.ok_calls or 0) / calls, 4) if calls else 0.0,
    }


async def usage_daily(db: AsyncSession, *, user_id: uuid.UUID, days: int = 7) -> list[dict]:
    """按天返回调用次数与 token（缺的日期不补，前端图表按已有数据画）。"""
    from datetime import timedelta

    from app.utils.time import today_local

    end = today_local()
    start = end - timedelta(days=days - 1)

    rows = (
        await db.execute(
            text(
                """
                SELECT (created_at AT TIME ZONE :tz)::date AS day,
                       COUNT(*) AS calls,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens
                FROM ai_usage
                WHERE user_id = :uid
                  AND (created_at AT TIME ZONE :tz)::date BETWEEN :start AND :end
                GROUP BY 1
                ORDER BY 1
                """
            ),
            {"uid": user_id, "tz": str(app_tz()), "start": start, "end": end},
        )
    ).all()

    return [
        {"date": row.day, "calls": int(row.calls), "total_tokens": int(row.total_tokens)}
        for row in rows
    ]
