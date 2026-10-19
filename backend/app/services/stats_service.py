"""学习数据统计（功能 11 的计算层；M6 的 HTTP 接口与 M5 的 agent 工具都复用它）。

口径约定（docs/api.md §12）：
- 任务完成率**不把 skipped 计入分母**（跳过不等于失败）
- 日期按 `APP_TIMEZONE` 切分，趋势数据**补零返回**（前端不用自己补点）
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiUsage, Material, Note, QuizAttempt, StudyTask
from app.utils.time import app_tz, today_local


def _as_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


async def _record_aggregate(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> dict:
    """学习时长相关聚合（按业务时区切日）。"""
    row = (
        await db.execute(
            text(
                """
                SELECT
                  COALESCE(SUM(duration_minutes), 0) AS total_minutes,
                  COUNT(DISTINCT (started_at AT TIME ZONE :tz)::date) AS active_days
                FROM study_record
                WHERE user_id = :uid
                  AND deleted_at IS NULL
                  AND (started_at AT TIME ZONE :tz)::date BETWEEN :start AND :end
                """
            ),
            {"uid": user_id, "tz": str(app_tz()), "start": start, "end": end},
        )
    ).one()
    return {"total_minutes": int(row.total_minutes or 0), "active_days": int(row.active_days or 0)}


async def _streak_days(db: AsyncSession, user_id: uuid.UUID) -> int:
    """连续学习天数：从今天往前数，直到某天没有学习记录。"""
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT (started_at AT TIME ZONE :tz)::date AS day
                FROM study_record
                WHERE user_id = :uid AND deleted_at IS NULL
                ORDER BY day DESC
                LIMIT 400
                """
            ),
            {"uid": user_id, "tz": str(app_tz())},
        )
    ).scalars().all()

    studied = set(rows)
    streak = 0
    cursor = today_local()
    while cursor in studied:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def overview(db: AsyncSession, *, user_id: uuid.UUID, days: int = 7) -> dict:
    """总览：给 /stats/overview 与 agent 工具 get_study_stats 共用。"""
    end = today_local()
    start = end - timedelta(days=days - 1)

    records = await _record_aggregate(db, user_id, start, end)

    task_row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(StudyTask.status == "done").label("done"),
            ).where(
                StudyTask.user_id == user_id,
                StudyTask.deleted_at.is_(None),
                StudyTask.status != "skipped",
                StudyTask.plan_date.between(start, end),
            )
        )
    ).one()

    quiz_row = (
        await db.execute(
            select(
                func.count().label("attempts"),
                func.coalesce(func.sum(QuizAttempt.correct_count), 0).label("correct"),
                func.coalesce(func.sum(QuizAttempt.question_count), 0).label("questions"),
            ).where(
                QuizAttempt.user_id == user_id,
                func.date(QuizAttempt.created_at) >= start,
                func.date(QuizAttempt.created_at) <= end,
            )
        )
    ).one()

    materials = await db.scalar(
        select(func.count()).select_from(Material).where(
            Material.user_id == user_id, Material.deleted_at.is_(None)
        )
    )
    notes = await db.scalar(
        select(func.count()).select_from(Note).where(
            Note.user_id == user_id, Note.deleted_at.is_(None)
        )
    )
    ai_calls = await db.scalar(
        select(func.count()).select_from(AiUsage).where(
            AiUsage.user_id == user_id,
            func.date(AiUsage.created_at) >= start,
            func.date(AiUsage.created_at) <= end,
        )
    )

    task_total = int(task_row.total or 0)
    task_done = int(task_row.done or 0)

    return {
        "period": {"from": start.isoformat(), "to": end.isoformat(), "days": days},
        "total_minutes": records["total_minutes"],
        "active_days": records["active_days"],
        "streak_days": await _streak_days(db, user_id),
        "daily_avg_minutes": round(records["total_minutes"] / days, 1) if days else 0.0,
        "task_total": task_total,
        "task_done": task_done,
        "task_completion_rate": _as_rate(task_done, task_total),
        "quiz_attempts": int(quiz_row.attempts or 0),
        "quiz_accuracy": _as_rate(int(quiz_row.correct or 0), int(quiz_row.questions or 0)),
        "materials": int(materials or 0),
        "notes": int(notes or 0),
        "ai_calls": int(ai_calls or 0),
    }


async def daily(db: AsyncSession, *, user_id: uuid.UUID, date_from: date, date_to: date) -> list[dict]:
    """每日趋势（缺的日期补零，前端直接用）。"""
    rows = (
        await db.execute(
            text(
                """
                WITH days AS (
                    SELECT generate_series(
                        CAST(:start AS date), CAST(:end AS date), interval '1 day'
                    )::date AS day
                )
                SELECT
                    d.day,
                    COALESCE((SELECT SUM(sr.duration_minutes) FROM study_record sr
                              WHERE sr.user_id = :uid AND sr.deleted_at IS NULL
                                AND (sr.started_at AT TIME ZONE :tz)::date = d.day), 0) AS minutes,
                    COALESCE((SELECT COUNT(*) FROM study_task st
                              WHERE st.user_id = :uid AND st.deleted_at IS NULL
                                AND st.status <> 'skipped' AND st.plan_date = d.day), 0) AS task_total,
                    COALESCE((SELECT COUNT(*) FROM study_task st
                              WHERE st.user_id = :uid AND st.deleted_at IS NULL
                                AND st.status = 'done' AND st.plan_date = d.day), 0) AS task_done,
                    COALESCE((SELECT COUNT(*) FROM quiz_attempt qa
                              WHERE qa.user_id = :uid
                                AND (qa.created_at AT TIME ZONE :tz)::date = d.day), 0) AS quiz_attempts,
                    COALESCE((SELECT SUM(qa.correct_count) FROM quiz_attempt qa
                              WHERE qa.user_id = :uid
                                AND (qa.created_at AT TIME ZONE :tz)::date = d.day), 0) AS quiz_correct,
                    COALESCE((SELECT SUM(qa.question_count) FROM quiz_attempt qa
                              WHERE qa.user_id = :uid
                                AND (qa.created_at AT TIME ZONE :tz)::date = d.day), 0) AS quiz_questions
                FROM days d
                ORDER BY d.day
                """
            ),
            {"uid": user_id, "tz": str(app_tz()), "start": date_from, "end": date_to},
        )
    ).all()

    return [
        {
            "date": row.day.isoformat(),
            "minutes": int(row.minutes),
            "task_total": int(row.task_total),
            "task_done": int(row.task_done),
            "quiz_attempts": int(row.quiz_attempts),
            "quiz_accuracy": _as_rate(int(row.quiz_correct), int(row.quiz_questions)),
        }
        for row in rows
    ]


async def subject_minutes(
    db: AsyncSession, *, user_id: uuid.UUID, date_from: date, date_to: date
) -> list[dict]:
    """按科目统计时长（用计划/任务的 subject，未分类归入「未分类」）。

    `task_done` 是该科目下**完成过的任务数**（同一天多次记录只算一次），
    契约 docs/api.md §12.1 `/stats/subjects` 要求返回它。
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(sp.subject, '未分类') AS subject,
                       SUM(sr.duration_minutes) AS minutes,
                       COUNT(DISTINCT st.id) FILTER (WHERE st.status = 'done') AS task_done
                FROM study_record sr
                LEFT JOIN study_task st ON st.id = sr.task_id
                LEFT JOIN study_plan sp ON sp.id = st.plan_id
                WHERE sr.user_id = :uid AND sr.deleted_at IS NULL
                  AND (sr.started_at AT TIME ZONE :tz)::date BETWEEN :start AND :end
                GROUP BY 1
                ORDER BY minutes DESC
                """
            ),
            {"uid": user_id, "tz": str(app_tz()), "start": date_from, "end": date_to},
        )
    ).all()
    return [
        {
            "subject": row.subject,
            "minutes": int(row.minutes),
            "task_done": int(row.task_done or 0),
        }
        for row in rows
    ]


async def weak_points(
    db: AsyncSession, *, user_id: uuid.UUID, days: int = 30, limit: int = 5, min_attempts: int = 3
) -> list[dict]:
    """薄弱知识点：按正确率升序取前 N（样本少于 min_attempts 的过滤掉，避免误导）。

    从 `quiz.question_data` 与 `quiz_attempt.answers` 两个 JSONB 展开后按 `no` 对齐
    —— 对应 docs/db.md §6 的示例查询。
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT qe.item ->> 'knowledge' AS knowledge,
                       COUNT(*) AS attempts,
                       COUNT(*) FILTER (WHERE (pa.item ->> 'is_correct')::boolean) AS correct
                FROM quiz_attempt a
                JOIN quiz q ON q.id = a.quiz_id
                CROSS JOIN LATERAL jsonb_array_elements(a.answers) AS pa(item)
                JOIN LATERAL jsonb_array_elements(q.question_data) AS qe(item)
                  ON (qe.item ->> 'no')::int = (pa.item ->> 'no')::int
                WHERE a.user_id = :uid
                  AND a.created_at >= now() - make_interval(days => :days)
                  AND COALESCE(qe.item ->> 'knowledge', '') <> ''
                GROUP BY 1
                HAVING COUNT(*) >= :min_attempts
                ORDER BY (COUNT(*) FILTER (WHERE (pa.item ->> 'is_correct')::boolean))::float / COUNT(*) ASC
                LIMIT :limit
                """
            ),
            {"uid": user_id, "days": days, "limit": limit, "min_attempts": min_attempts},
        )
    ).all()

    return [
        {
            "knowledge": row.knowledge,
            "attempts": int(row.attempts),
            "correct": int(row.correct),
            "accuracy": _as_rate(int(row.correct), int(row.attempts)),
        }
        for row in rows
    ]
