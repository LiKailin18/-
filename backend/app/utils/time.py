"""日期与时区工具。

约定（CLAUDE.md §6）：数据库存 UTC，但「今天」「本周」这类业务概念必须按
`APP_TIMEZONE`（默认 Asia/Shanghai）计算 —— 直接用 date.today() 会在凌晨取到前一天。
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def app_tz() -> ZoneInfo:
    return ZoneInfo(settings.app_timezone)


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_local() -> datetime:
    return datetime.now(app_tz())


def today_local() -> date:
    """业务意义上的「今天」。"""
    return now_local().date()


def date_range(start: date, end: date) -> list[date]:
    """闭区间 [start, end] 的日期列表。"""
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]
