"""Alembic 迁移环境（异步）。

约定见 CLAUDE.md §6 / docs/db.md §7：
- 连接串只从应用配置读取（backend/.env），不在 alembic.ini 里写密码
- 目标 metadata 固定为 SQLModel.metadata
- **必须 import app.models 包**：它统一导出全部表模型；漏了就会 autogenerate 漏表
- 传 compare_type：让列类型变更也能被 autogenerate 发现
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from app.core.config import settings
from app.models import *  # 全部表模型统一在此导入（忽略规则见 pyproject.toml）

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用应用配置覆盖 ini 中的占位连接串
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = SQLModel.metadata


def render_item(type_, obj, autogen_context):
    """修正 SQLModel 自定义类型的渲染。

    SQLModel 的 `AutoString` 默认会被渲染成 `sqlmodel.sql.sqltypes.AutoString(...)`，
    但迁移模板里没有 `import sqlmodel`，直接执行会 NameError（CLAUDE.md §11）。
    这里统一降级成标准 `sa.String`，让迁移文件只依赖 sqlalchemy。
    """
    is_sqlmodel_type = type_ == "type" and obj.__class__.__module__.startswith("sqlmodel")
    if is_sqlmodel_type and obj.__class__.__name__ == "AutoString":
        return f"sa.String(length={getattr(obj, 'length', None)})"
    return False


def run_migrations_offline() -> None:
    """离线模式：只输出 SQL，不连数据库（用于产出建表脚本）。"""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
