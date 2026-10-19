"""个性化学习推荐（功能 10 的**规则层**；契约：docs/api.md §12.2）。

设计要点：

- **不调用大模型**：秒回、可解释、可复现、不消耗 AI 配额；叙述性的深度建议走
  M5 的 `POST /ai/advice/generate`（两条线互补，互不替代）
- 每条推荐都必须能说清「为什么推它」：`reason` 由数据直接算出，不写空话套话
- 只读：本模块不写任何表，也不改用户数据
- 复用 `stats_service` 的口径（时长、薄弱点），**不另写一份聚合 SQL**
"""

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Material, StudyPlan, StudyTask
from app.services import stats_service
from app.utils.time import app_tz, today_local

# 优先级：数字越小越靠前（前端按数组顺序展示即可）
PRIORITY: dict[str, int] = {
    "task": 1,      # 今天/逾期还没做的任务 —— 最该先干的事
    "review": 2,    # 有薄弱知识点 —— 补短板
    "plan": 3,      # 计划推进
    "material": 4,  # 资料没解析好（AI 读不到正文）
    "habit": 5,     # 学习习惯/时长不足
}

WEAK_ACCURACY = 0.6   # 正确率低于它才算「薄弱」
HABIT_RATIO = 0.5     # 近 7 天时长低于「目标 × 7 × 该比例」→ 建议降低启动门槛


async def _task_tip(db: AsyncSession, user_id: uuid.UUID, today) -> dict | None:
    """最紧急的未完成任务：逾期的排在今天的前面，同一天先推预估时长更长的。"""
    row = (
        await db.execute(
            select(StudyTask, StudyPlan.title)
            .join(StudyPlan, StudyPlan.id == StudyTask.plan_id, isouter=True)
            .where(
                StudyTask.user_id == user_id,
                StudyTask.deleted_at.is_(None),
                StudyTask.status.in_(("pending", "doing")),
                StudyTask.plan_date <= today,
            )
            .order_by(StudyTask.plan_date.asc(), StudyTask.est_minutes.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None

    task, plan_title = row
    overdue_days = (today - task.plan_date).days
    if overdue_days > 0:
        reason = f"「{plan_title or '未归属计划'}」的这个任务已逾期 {overdue_days} 天"
    else:
        reason = f"这是今天的任务（预估 {task.est_minutes} 分钟），先把它做掉"
    return {
        "kind": "task",
        "priority": PRIORITY["task"],
        "title": f"先完成「{task.title}」",
        "reason": reason,
        "action": "去完成任务",
        "route": "/plans?tab=tasks",
        "ref_id": str(task.id),
    }


async def _weak_material(db: AsyncSession, user_id: uuid.UUID, knowledge: str) -> dict | None:
    """找到「考过这个知识点」的最近一份题，从而定位到它属于哪份资料。"""
    row = (
        await db.execute(
            text(
                """
                SELECT q.material_id AS material_id, m.title AS material_title
                FROM quiz q
                LEFT JOIN material m ON m.id = q.material_id
                WHERE q.user_id = :uid
                  AND q.deleted_at IS NULL
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(q.question_data) AS e
                      WHERE e ->> 'knowledge' = :kp
                  )
                ORDER BY q.created_at DESC
                LIMIT 1
                """
            ),
            {"uid": user_id, "kp": knowledge},
        )
    ).first()
    return {"material_id": row.material_id, "material_title": row.material_title} if row else None


async def _review_tip(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    """薄弱知识点：正确率低于阈值的第一个（`weak_points` 已按正确率升序）。"""
    points = await stats_service.weak_points(db, user_id=user_id, days=30, limit=5)
    weak = next((point for point in points if point["accuracy"] < WEAK_ACCURACY), None)
    if weak is None:
        return None

    source = await _weak_material(db, user_id, weak["knowledge"])
    where = source["material_title"] if source and source["material_title"] else "相关资料"
    return {
        "kind": "review",
        "priority": PRIORITY["review"],
        "title": f"复习「{weak['knowledge']}」（正确率 {weak['accuracy'] * 100:.0f}%）",
        "reason": (
            f"近 30 天在「{weak['knowledge']}」上做了 {weak['attempts']} 题，"
            f"只对 {weak['correct']} 题；出处：《{where}》"
        ),
        "action": "打开资料复习",
        "route": "/materials",
        "ref_id": str(source["material_id"]) if source and source["material_id"] else None,
    }


async def _plan_tip(db: AsyncSession, user_id: uuid.UUID, today) -> dict | None:
    """推进进行中的计划（按结束日期最近优先）。"""
    plan = (
        await db.execute(
            select(StudyPlan)
            .where(
                StudyPlan.user_id == user_id,
                StudyPlan.deleted_at.is_(None),
                StudyPlan.status.in_(("active", "draft")),
            )
            .order_by(StudyPlan.end_date.asc())
            .limit(1)
        )
    ).scalars().first()
    if plan is None:
        return None

    left = (plan.end_date - today).days
    if plan.status == "draft":
        reason = "这份计划还是草稿状态，生成每日任务后才会出现在「每日任务」里"
        action = "去激活计划"
    elif left < 0:
        reason = f"计划已于 {plan.end_date.isoformat()} 到期，建议回顾或延长"
        action = "去调整计划"
    else:
        done = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FILTER (WHERE status = 'done') AS done,
                           COUNT(*) AS total
                    FROM study_task
                    WHERE plan_id = :pid AND deleted_at IS NULL AND status <> 'skipped'
                    """
                ),
                {"pid": plan.id},
            )
        ).one()
        total = int(done.total or 0)
        done_count = int(done.done or 0)
        rate = (done_count / total) if total else 0.0
        reason = f"计划还剩 {left} 天，任务完成率 {rate * 100:.0f}%（{done_count}/{total}）"
        action = "去推进计划"
    return {
        "kind": "plan",
        "priority": PRIORITY["plan"],
        "title": f"推进计划「{plan.title}」",
        "reason": reason,
        "action": action,
        "route": "/plans",
        "ref_id": str(plan.id),
    }


async def _material_tip(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    """解析没成功的资料：AI 读不到正文，会直接影响总结/出题/问答。"""
    material = (
        await db.execute(
            select(Material)
            .where(
                Material.user_id == user_id,
                Material.deleted_at.is_(None),
                Material.parse_status != "success",
            )
            .order_by(Material.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if material is None:
        return None

    status_text = {
        "pending": "还没解析",
        "parsing": "正在解析",
        "failed": "解析失败",
        "unsupported": "是扫描件，不支持文本解析",
    }.get(material.parse_status, material.parse_status)
    return {
        "kind": "material",
        "priority": PRIORITY["material"],
        "title": f"处理资料「{material.title}」",
        "reason": f"这份资料{status_text}，AI 总结 / 出题 / 问答都读不到它的正文",
        "action": "去重新解析",
        "route": "/materials",
        "ref_id": str(material.id),
    }


async def _habit_tip(
    db: AsyncSession, user_id: uuid.UUID, *, daily_target_minutes: int
) -> dict | None:
    """时长明显不足时，给一个「小到不可能失败」的行动（降低启动门槛）。"""
    data = await stats_service.overview(db, user_id=user_id, days=7)
    target = daily_target_minutes * 7 * HABIT_RATIO
    if data["total_minutes"] >= target:
        return None

    return {
        "kind": "habit",
        "priority": PRIORITY["habit"],
        "title": "先来一个 25 分钟的番茄钟",
        "reason": (
            f"近 7 天只学了 {data['total_minutes']} 分钟"
            f"（目标 {daily_target_minutes} 分钟/天，连续 {data['streak_days']} 天）"
        ),
        "action": "去记一次学习",
        "route": "/plans?tab=records",
        "ref_id": None,
    }


async def build(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    daily_target_minutes: int,
    limit: int = 5,
) -> list[dict]:
    """按优先级产出推荐（每个 kind 最多 1 条，`limit` 截断）。"""
    today = today_local()
    candidates = [
        await _task_tip(db, user_id, today),
        await _review_tip(db, user_id),
        await _plan_tip(db, user_id, today),
        await _material_tip(db, user_id),
        await _habit_tip(db, user_id, daily_target_minutes=daily_target_minutes),
    ]
    items = [item for item in candidates if item is not None]
    items.sort(key=lambda item: item["priority"])
    return items[:limit]


def generated_at() -> datetime:
    """生成时间（业务时区），前端直接显示。"""
    return datetime.now(app_tz())
