"""FastAPI 应用入口。

职责：创建应用、注册中间件与异常处理、挂载路由。
业务逻辑一律放在 services 层，本文件不写业务（CLAUDE.md §5.1）。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.db.engine import engine
from app.schemas.error import ErrorOut

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "启动 %s v%s (env=%s, tz=%s)",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.app_timezone,
    )
    yield
    await engine.dispose()
    logger.info("已释放数据库连接池")


app = FastAPI(
    title="智能学习系统 API",
    version=settings.app_version,
    description="基于大语言模型的智能学习系统后端（本科毕业设计）",
    lifespan=lifespan,
)

# 开发期允许前端 dev server 直连；生产由 nginx 同源代理，不产生跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
# 显式声明 422 的响应模型，覆盖 FastAPI 自动生成的 {"detail": [...]} 形状，
# 让 Swagger 显示的与实际返回的 {code, message, detail} 一致（契约 docs/api.md §1.3）
app.include_router(
    api_v1_router,
    prefix="/api/v1",
    responses={
        422: {
            "model": ErrorOut,
            "description": "请求参数校验失败（code=SYS_422，detail 为字段级错误）",
        }
    },
)

# 统一错误体 {code, message, detail}（契约 docs/api.md §1.3）
register_exception_handlers(app)
