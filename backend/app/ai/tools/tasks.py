"""待办任务工具（契约：docs/agent-tools.md §3.5）。"""

import uuid

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import task_service
from app.utils.time import today_local

VALID_STATUSES = ("pending", "doing", "done", "skipped")


def make_list_pending_tasks(user_id: uuid.UUID, db: AsyncSession):
    """列出指定日期的任务；默认「今天」按业务时区计算。"""

    @tool
    async def list_pending_tasks(
        plan_date: str | None = None, status: str = "pending", limit: int = 10
    ) -> dict:
        """List the user's tasks for a date (YYYY-MM-DD, defaults to today).

        status is one of pending / doing / done / skipped.
        """
        if status not in VALID_STATUSES:
            return {
                "ok": False,
                "error": "BAD_STATUS",
                "message": f"status 必须是 {', '.join(VALID_STATUSES)} 之一",
            }

        if plan_date:
            try:
                target = date_from_string(plan_date)
            except ValueError:
                return {
                    "ok": False,
                    "error": "BAD_DATE",
                    "message": "日期格式应为 YYYY-MM-DD",
                }
        else:
            # ⚠️ 「今天」必须按业务时区算，不能用 UTC 日期
            target = today_local()

        safe_limit = max(1, min(limit, 20))
        tasks, _total = await task_service.list_tasks(
            db, user_id=user_id, offset=0, limit=safe_limit, plan_date=target, status=status
        )
        payload = [
            {
                "id": str(task.id),
                "title": task.title,
                "est_minutes": task.est_minutes,
                "status": task.status,
                "plan_id": str(task.plan_id) if task.plan_id else None,
                "material_id": str(task.material_id) if task.material_id else None,
            }
            for task in tasks
        ]
        return {
            "ok": True,
            "data": {"date": target.isoformat(), "tasks": payload},
            "meta": {"count": len(payload), "truncated": False},
        }

    return list_pending_tasks


def date_from_string(value: str):
    """把 YYYY-MM-DD 解析成 date（独立出来便于单测）。"""
    from datetime import date as date_type

    return date_type.fromisoformat(value)
