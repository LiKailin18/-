"""数据库引擎与连通性检查。

约定见 CLAUDE.md §11：
- 统一异步（asyncpg + AsyncSession），不混用同步 Session
- expire_on_commit=False：提交后对象仍可读
- pool_pre_ping=True：连接被回收后自动重建
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def check_db() -> bool:
    """探测数据库是否可用。

    健康检查专用，必须吞掉所有异常（否则数据库不可用时接口会 500 而不是 503）。
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        # 这里就是要兜住一切异常：数据库不可用时健康检查必须返回 503 而不是 500
        logger.warning("数据库不可用: %s: %s", type(exc).__name__, exc)
        return False
    return True
