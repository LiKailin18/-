"""个性化学习建议（功能 10）。

关键约束（docs/agent-tools.md §4.3）：**能用 SQL 算出来的东西不交给模型生成** ——
薄弱知识点与未来 7 天安排都由后端算好后覆盖模型输出，模型只负责解释与措辞。
"""

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import usage as usage_module
from app.ai.schemas import AdviceOut
from app.ai.validators import AdviceInvalidError, apply_advice_overrides
from app.core.config import settings
from app.core.exceptions import NotFound
from app.models import AiGeneration, AppUser
from app.schemas.ai import AdviceGenerateIn
from app.services import ai_common, stats_service, task_service
from app.utils.time import today_local

FOCUS_HINTS = {
    "review": "侧重复习与查漏补缺",
    "plan": "侧重下一阶段的时间安排",
    "balance": "兼顾复习与新课推进",
}


def _build_next_days(weak_points: list[dict], daily_minutes: int) -> list[dict]:
    """后端算未来 7 天安排：优先补最弱的知识点。"""
    today = today_local()
    focus_pool = [point["knowledge"] for point in weak_points] or ["复习近期内容"]
    return [
        {
            "date": (today + timedelta(days=offset)).isoformat(),
            "minutes": daily_minutes,
            "focus": focus_pool[offset % len(focus_pool)],
        }
        for offset in range(7)
    ]


async def generate(
    db: AsyncSession, *, user: AppUser, data: AdviceGenerateIn
) -> tuple[AiGeneration, int]:
    await usage_module.ensure_quota(db, user_id=user.id)

    overview = await stats_service.overview(db, user_id=user.id, days=data.days)
    weak_points = await stats_service.weak_points(db, user_id=user.id, days=max(data.days, 30))
    pending, pending_total = await task_service.list_tasks(
        db, user_id=user.id, offset=0, limit=10, status="pending"
    )
    next_7_days = _build_next_days(weak_points, user.daily_target_minutes)

    context = (
        f"统计窗口：近 {data.days} 天（侧重：{FOCUS_HINTS[data.focus]}）\n"
        f"学习时长：{overview['total_minutes']} 分钟，活跃 {overview['active_days']} 天，"
        f"连续 {overview['streak_days']} 天\n"
        f"任务：{overview['task_done']}/{overview['task_total']} 完成"
        f"（完成率 {overview['task_completion_rate']}）\n"
        f"测验：{overview['quiz_attempts']} 次，正确率 {overview['quiz_accuracy']}\n"
        f"薄弱知识点（正确率升序）：{weak_points or '样本不足'}\n"
        f"当前待办任务：{[task.title for task in pending]}（共 {pending_total} 个）\n"
        f"用户每日目标：{user.daily_target_minutes} 分钟\n"
    )

    def validator(result: AdviceOut) -> AdviceOut:
        return apply_advice_overrides(
            result,
            weak_points=weak_points,
            next_7_days=next_7_days,
            daily_target_minutes=user.daily_target_minutes,
        )

    result, usage, retries = await ai_common.structured_with_retry(
        "advice",
        user_id=user.id,
        db=db,
        message=(
            "以下是用户的学习数据（请先用工具核实，再给建议）：\n\n"
            f"{context}\n"
            "请给出总结与 2-6 条可执行建议，至少一条 high 优先级。"
        ),
        validator=validator,
        invalid_errors=(AdviceInvalidError,),
    )

    row = AiGeneration(
        user_id=user.id,
        scene="advice",
        ref_type="user",
        ref_id=user.id,
        input_params={"days": data.days, "focus": data.focus},
        output_md=result.summary,
        output_data={
            "summary": result.summary,
            "suggestions": [item.model_dump() for item in result.suggestions],
            "weak_points": result.weak_points,
            "next_7_days": result.next_7_days,
            "stats_snapshot": overview,
            "period_days": data.days,
            "focus": data.focus,
        },
        model=settings.llm_model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=usage.latency_ms,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await usage_module.record_usage(
        db, user_id=user.id, scene="advice", model=settings.llm_model, usage=usage
    )
    return row, retries


async def latest(db: AsyncSession, user_id: uuid.UUID) -> AiGeneration | None:
    return await db.scalar(
        select(AiGeneration)
        .where(AiGeneration.user_id == user_id, AiGeneration.scene == "advice")
        .order_by(AiGeneration.created_at.desc())
        .limit(1)
    )


async def get_owned(db: AsyncSession, user_id: uuid.UUID, advice_id: uuid.UUID) -> AiGeneration:
    row = await db.scalar(
        select(AiGeneration).where(
            AiGeneration.id == advice_id,
            AiGeneration.user_id == user_id,
            AiGeneration.scene == "advice",
        )
    )
    if row is None:
        raise NotFound("学习建议不存在")
    return row


async def history(
    db: AsyncSession, *, user_id: uuid.UUID, offset: int, limit: int
) -> tuple[list[AiGeneration], int]:
    conditions = [AiGeneration.user_id == user_id, AiGeneration.scene == "advice"]
    total = await db.scalar(select(func.count()).select_from(AiGeneration).where(*conditions))
    rows = (
        await db.execute(
            select(AiGeneration)
            .where(*conditions)
            .order_by(AiGeneration.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total or 0)
