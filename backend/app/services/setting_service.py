"""系统配置读写（功能 13.5；契约：docs/api.md §16.5 / docs/db.md §3.13）。

两条设计要点：

1. **60 秒进程内缓存**：配置在每个请求里都可能被读到（AI 开关、配额、上传上限），
   每次都打库没有必要；写操作立即清缓存，所以「改完马上生效」。
2. **类型与范围校验按 `value_type` 走**：`int` 1..10000、`bool` 必须布尔、`string` ≤200 字。
   `editable=false` 的键（`ai.model_name`）拒绝写入 —— 运行时切模型会让历史
   `model` 字段无法解释、计费口径漂移。

读取失败（键不存在 / 类型不对）一律回落到 `.env` 的默认值：配置表是**覆盖层**，
不是唯一真相，这样清库重建也不会把功能弄挂。
"""

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequest
from app.models import AppSetting, AppUser

CACHE_TTL_SECONDS = 60

# 键 → (默认值, editable)。默认值来自 .env，配置表没有记录时用它
DEFAULTS: dict[str, tuple[Any, bool]] = {
    "ai.daily_quota": (settings.ai_daily_quota, True),
    "ai.enabled": (True, True),
    "ai.model_name": (settings.llm_model, False),  # 只读展示位
    "register.allow": (True, True),
    "upload.max_mb": (settings.max_upload_mb, True),
}

INT_MIN, INT_MAX = 1, 10000
STRING_MAX = 200


class _Cache:
    """极简 TTL 缓存：只缓存标量，配置总量很小（个位数键）。"""

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._expires_at: float = 0.0

    def get(self, key: str) -> Any | None:
        if time.monotonic() >= self._expires_at:
            return None
        return self._values.get(key)

    def put(self, values: dict[str, Any]) -> None:
        self._values = values
        self._expires_at = time.monotonic() + CACHE_TTL_SECONDS

    def clear(self) -> None:
        self._values = {}
        self._expires_at = 0.0


_cache = _Cache()


def _coerce(key: str, raw: Any, value_type: str) -> Any:
    """把 JSONB 里的值转成正确的 Python 类型（写错的配置不至于把接口打挂）。"""
    default = DEFAULTS.get(key, (None, True))[0]
    try:
        if value_type == "int":
            return int(raw)
        if value_type == "bool":
            return bool(raw)
        return raw if isinstance(raw, str) else str(raw)
    except (TypeError, ValueError):
        return default


def validate_value(key: str, value: Any) -> Any:
    """按 value_type 校验并归一化；不合法直接 400。"""
    default, editable = DEFAULTS.get(key, (None, True))
    if not editable:
        raise BadRequest(f"配置 {key} 为只读（改模型请修改后端 .env 并重启服务）")

    if default is None:
        raise BadRequest(f"未知配置项：{key}")

    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise BadRequest(f"{key} 需要布尔值（true / false）")
        return value

    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise BadRequest(f"{key} 需要整数")
        if not INT_MIN <= value <= INT_MAX:
            raise BadRequest(f"{key} 必须在 {INT_MIN}..{INT_MAX} 之间")
        return value

    if not isinstance(value, str) or len(value) > STRING_MAX:
        raise BadRequest(f"{key} 需要不超过 {STRING_MAX} 字的字符串")
    return value


async def load_all(db: AsyncSession) -> dict[str, Any]:
    """读全部配置（带缓存）：返回 key → 值，缺的用默认值补上。"""
    values = {key: default for key, (default, _editable) in DEFAULTS.items()}

    cached = all(_cache.get(key) is not None for key in DEFAULTS)
    if cached:
        return {**values, **{key: _cache.get(key) for key in DEFAULTS}}

    rows = (await db.execute(select(AppSetting))).scalars().all()
    for row in rows:
        if row.key not in DEFAULTS:
            continue
        _default, editable = DEFAULTS[row.key]
        if not editable:
            # 只读项（如 ai.model_name）永远以**部署配置**为准：
            # 库里那行只是历史记录，不能覆盖 .env 里的真实模型
            continue
        values[row.key] = _coerce(row.key, row.value, row.value_type)
    _cache.put(values)
    return values


async def get_value(db: AsyncSession, key: str) -> Any:
    return (await load_all(db)).get(key, DEFAULTS.get(key, (None, True))[0])


async def get_int(db: AsyncSession, key: str) -> int:
    return int(await get_value(db, key))


async def get_bool(db: AsyncSession, key: str) -> bool:
    return bool(await get_value(db, key))


async def is_enabled(db: AsyncSession, key: str) -> bool:
    """开关类配置的统一读法（ai.enabled / register.allow）。"""
    return await get_bool(db, key)


async def list_settings(db: AsyncSession) -> list[dict]:
    """给管理端列表用：补上 value_type / description / editable / 最后修改人。"""
    rows = (await db.execute(select(AppSetting))).scalars().all()
    by_key = {row.key: row for row in rows}
    live = await load_all(db)

    names: dict[uuid.UUID, str] = {}
    admin_ids = [row.updated_by for row in rows if row.updated_by]
    if admin_ids:
        users = (
            await db.execute(select(AppUser.id, AppUser.username).where(AppUser.id.in_(admin_ids)))
        ).all()
        names = {row.id: row.username for row in users}

    items: list[dict] = []
    for key, (default, editable) in DEFAULTS.items():
        row = by_key.get(key)
        updater = names.get(row.updated_by) if row and row.updated_by else None
        items.append(
            {
                "key": key,
                "value": live.get(key, default),
                "value_type": row.value_type if row else _guess_type(default),
                "description": row.description if row else "",
                "editable": editable,
                "updated_at": row.updated_at if row else None,
                "updated_by_username": updater,
            }
        )
    return sorted(items, key=lambda item: item["key"])


def _guess_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    return "string"


async def update_settings(
    db: AsyncSession, *, admin: AppUser, changes: list[tuple[str, Any]]
) -> list[dict]:
    """批量改配置；返回变更快照（给审计用）。**不 commit**，由调用方与审计一起提交。"""
    snapshot: list[dict] = []
    for key, value in changes:
        normalized = validate_value(key, value)

        row = await db.get(AppSetting, key)
        if row is None:
            row = AppSetting(
                key=key,
                value=normalized,
                value_type=_guess_type(DEFAULTS[key][0]),
                description="",
            )
            db.add(row)
            before: Any = None
        else:
            before = _coerce(key, row.value, row.value_type)
            row.value = normalized

        row.updated_by = admin.id
        from app.models.user import utcnow

        row.updated_at = utcnow()
        snapshot.append({"key": key, "from": before, "to": normalized})

    await db.flush()
    _cache.clear()  # 立即生效，不等 TTL 到期
    return snapshot
