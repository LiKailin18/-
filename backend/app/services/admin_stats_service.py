"""管理端统计聚合（功能 13.1 仪表盘 / 13.4 AI 用量；契约：docs/api.md §16.1、§16.4）。

口径（写进论文时可直接引用）：

- **活跃用户**：近 7 天有登录（`last_login_at`）；日活的定义是「当天有学习记录」，
  因为登录时间只有一个时间戳，无法事后按天还原，而学习记录天然带日期
- **内容数**：全部软删除过滤（`deleted_at IS NULL`）
- **完成率**：`skipped` 不进分母（与用户端口径一致）
- **AI 成功率**：`ok=true` 的调用数 / 总调用数；失败也计次（它们同样消耗了请求）
- 日期一律按 `APP_TIMEZONE` 切分，趋势数据补零
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiUsage, AppUser, Material, Note, Quiz, StudyPlan, StudyTask
from app.utils.time import app_tz, today_local


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


async def overview(db: AsyncSession, *, days: int = 30) -> dict:
    """13.1 仪表盘概览。"""
    end = today_local()
    start = end - timedelta(days=days - 1)
    tz = str(app_tz())
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)

    users = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(AppUser.last_login_at >= week_ago).label("active_7d"),
                func.count().filter(AppUser.created_at >= week_ago).label("new_7d"),
                func.count().filter(AppUser.is_active.is_(False)).label("disabled"),
                func.count().filter(AppUser.role == "admin").label("admins"),
            )
        )
    ).one()

    content = (
        await db.execute(
            select(
                select(func.count())
                .select_from(Material)
                .where(Material.deleted_at.is_(None))
                .scalar_subquery()
                .label("materials"),
                select(func.count())
                .select_from(Note)
                .where(Note.deleted_at.is_(None))
                .scalar_subquery()
                .label("notes"),
                select(func.count())
                .select_from(StudyPlan)
                .where(StudyPlan.deleted_at.is_(None))
                .scalar_subquery()
                .label("plans"),
                select(func.count())
                .select_from(Quiz)
                .where(Quiz.deleted_at.is_(None))
                .scalar_subquery()
                .label("quizzes"),
            )
        )
    ).one()

    minutes = await db.scalar(
        text(
            """
            SELECT COALESCE(SUM(sr.duration_minutes), 0)
            FROM study_record sr
            WHERE sr.deleted_at IS NULL
              AND (sr.started_at AT TIME ZONE :tz)::date BETWEEN :start AND :end
            """
        ),
        {"tz": tz, "start": start, "end": end},
    )

    tasks = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(StudyTask.status == "done").label("done"),
            ).where(
                StudyTask.deleted_at.is_(None),
                StudyTask.status != "skipped",
                StudyTask.plan_date.between(start, end),
            )
        )
    ).one()

    ai = (
        await db.execute(
            select(
                func.count().label("calls"),
                func.coalesce(func.sum(AiUsage.total_tokens), 0).label("tokens"),
                func.count().filter(AiUsage.ok.is_(True)).label("ok_calls"),
            ).where(
                func.date(AiUsage.created_at.op("AT TIME ZONE")(tz)).between(start, end)
            )
        )
    ).one()

    today_calls = await db.scalar(
        select(func.count())
        .select_from(AiUsage)
        .where(func.date(AiUsage.created_at.op("AT TIME ZONE")(tz)) == end)
    )

    task_total = int(tasks.total or 0)
    task_done = int(tasks.done or 0)
    calls = int(ai.calls or 0)

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "days": days},
        "users": {
            "total": int(users.total or 0),
            "active_7d": int(users.active_7d or 0),
            "new_7d": int(users.new_7d or 0),
            "disabled": int(users.disabled or 0),
            "admins": int(users.admins or 0),
        },
        "content": {
            "materials": int(content.materials or 0),
            "notes": int(content.notes or 0),
            "plans": int(content.plans or 0),
            "quizzes": int(content.quizzes or 0),
        },
        "activity": {
            "study_minutes": int(minutes or 0),
            "task_completion_rate": _rate(task_done, task_total),
        },
        "ai": {
            "calls": calls,
            "total_tokens": int(ai.tokens or 0),
            "success_rate": _rate(int(ai.ok_calls or 0), calls),
            "today_calls": int(today_calls or 0),
        },
    }


async def daily(db: AsyncSession, *, date_from: date, date_to: date) -> list[dict]:
    """13.1 每日趋势（新用户 / 日活 / 学习时长 / AI 调用），缺的日期补零。"""
    rows = (
        await db.execute(
            text(
                """
                WITH days AS (
                    SELECT generate_series(
                        CAST(:start AS date), CAST(:end AS date), interval '1 day'
                    )::date AS day
                )
                SELECT d.day,
                    (SELECT COUNT(*) FROM app_user u
                     WHERE (u.created_at AT TIME ZONE :tz)::date = d.day) AS new_users,
                    (SELECT COUNT(DISTINCT sr.user_id) FROM study_record sr
                     WHERE sr.deleted_at IS NULL
                       AND (sr.started_at AT TIME ZONE :tz)::date = d.day) AS active_users,
                    COALESCE((SELECT SUM(sr.duration_minutes) FROM study_record sr
                     WHERE sr.deleted_at IS NULL
                       AND (sr.started_at AT TIME ZONE :tz)::date = d.day), 0) AS study_minutes,
                    (SELECT COUNT(*) FROM ai_usage a
                     WHERE (a.created_at AT TIME ZONE :tz)::date = d.day) AS ai_calls
                FROM days d
                ORDER BY d.day
                """
            ),
            {"tz": str(app_tz()), "start": date_from, "end": date_to},
        )
    ).all()

    return [
        {
            "date": row.day,
            "new_users": int(row.new_users),
            "active_users": int(row.active_users),
            "study_minutes": int(row.study_minutes),
            "ai_calls": int(row.ai_calls),
        }
        for row in rows
    ]


async def ai_breakdown(db: AsyncSession, *, days: int = 30) -> dict:
    """13.4 按场景 / 用户 / 日期三个维度的 AI 用量。"""
    end = today_local()
    start = end - timedelta(days=days - 1)
    params = {"tz": str(app_tz()), "start": start, "end": end}

    by_scene = (
        await db.execute(
            text(
                """
                SELECT scene,
                       COUNT(*) AS calls,
                       COALESCE(SUM(total_tokens), 0) AS tokens,
                       COUNT(*) FILTER (WHERE ok) AS ok_calls,
                       COALESCE(AVG(latency_ms), 0) AS avg_latency
                FROM ai_usage
                WHERE (created_at AT TIME ZONE :tz)::date BETWEEN :start AND :end
                GROUP BY scene
                ORDER BY calls DESC
                """
            ),
            params,
        )
    ).all()

    top_users = (
        await db.execute(
            text(
                """
                SELECT u.id AS user_id, u.username,
                       COUNT(*) AS calls,
                       COALESCE(SUM(a.total_tokens), 0) AS tokens
                FROM ai_usage a
                JOIN app_user u ON u.id = a.user_id
                WHERE (a.created_at AT TIME ZONE :tz)::date BETWEEN :start AND :end
                GROUP BY u.id, u.username
                ORDER BY calls DESC, tokens DESC
                LIMIT 10
                """
            ),
            params,
        )
    ).all()

    daily_rows = (
        await db.execute(
            text(
                """
                WITH days AS (
                    SELECT generate_series(
                        CAST(:start AS date), CAST(:end AS date), interval '1 day'
                    )::date AS day
                )
                SELECT d.day,
                       COALESCE((SELECT COUNT(*) FROM ai_usage a
                         WHERE (a.created_at AT TIME ZONE :tz)::date = d.day), 0) AS calls,
                       COALESCE((SELECT SUM(a.total_tokens) FROM ai_usage a
                         WHERE (a.created_at AT TIME ZONE :tz)::date = d.day), 0) AS tokens,
                       COALESCE((SELECT COUNT(*) FROM ai_usage a
                         WHERE (a.created_at AT TIME ZONE :tz)::date = d.day
                           AND NOT a.ok), 0) AS failed
                FROM days d
                ORDER BY d.day
                """
            ),
            params,
        )
    ).all()

    return {
        "by_scene": [
            {
                "scene": row.scene,
                "calls": int(row.calls),
                "total_tokens": int(row.tokens),
                "success_rate": _rate(int(row.ok_calls), int(row.calls)),
                "avg_latency_ms": round(float(row.avg_latency or 0)),
            }
            for row in by_scene
        ],
        "top_users": [
            {
                "user_id": row.user_id,
                "username": row.username,
                "calls": int(row.calls),
                "total_tokens": int(row.tokens),
            }
            for row in top_users
        ],
        "daily": [
            {
                "date": row.day,
                "calls": int(row.calls),
                "total_tokens": int(row.tokens),
                "failed": int(row.failed),
            }
            for row in daily_rows
        ],
    }


async def list_ai_usage(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
    user_id=None,
    scene: str | None = None,
    ok: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[dict], int]:
    """13.4 调用明细（分页 + 筛选）。"""
    conditions = []
    if user_id:
        conditions.append(AiUsage.user_id == user_id)
    if scene:
        conditions.append(AiUsage.scene == scene)
    if ok is not None:
        conditions.append(AiUsage.ok.is_(ok))
    if date_from:
        conditions.append(
            func.date(AiUsage.created_at.op("AT TIME ZONE")(str(app_tz()))) >= date_from
        )
    if date_to:
        conditions.append(
            func.date(AiUsage.created_at.op("AT TIME ZONE")(str(app_tz()))) <= date_to
        )

    total = await db.scalar(select(func.count()).select_from(AiUsage).where(*conditions))
    rows = (
        await db.execute(
            select(AiUsage, AppUser.username)
            .join(AppUser, AppUser.id == AiUsage.user_id, isouter=True)
            .where(*conditions)
            .order_by(AiUsage.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [
        {
            "id": row.AiUsage.id,
            "user": {"id": row.AiUsage.user_id, "username": row.username or "（已删除）"},
            "scene": row.AiUsage.scene,
            "model": row.AiUsage.model,
            "prompt_tokens": row.AiUsage.prompt_tokens,
            "completion_tokens": row.AiUsage.completion_tokens,
            "total_tokens": row.AiUsage.total_tokens,
            "steps": row.AiUsage.steps,
            "latency_ms": row.AiUsage.latency_ms,
            "ok": row.AiUsage.ok,
            "error_code": row.AiUsage.error_code,
            "created_at": row.AiUsage.created_at,
        }
        for row in rows
    ]
    return items, int(total or 0)
