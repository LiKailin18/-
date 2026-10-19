"""健康检查接口（契约：docs/api.md §1.6）。

- 路径是根级的 /health，不带 /api/v1 前缀，供容器 healthcheck 与前端首屏连通性检查使用
- 数据库不可用时返回 503，让容器编排能判断「未就绪」
- 响应体固定为 {status, db, version}；原始异常只写日志，不外传给调用方
"""

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.db.engine import check_db
from app.schemas.health import HealthOut

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="健康检查",
    response_model=HealthOut,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthOut,
            "description": "数据库不可用：status=degraded, db=down",
        }
    },
)
async def health(response: Response) -> HealthOut:
    db_ok = await check_db()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(
        status="ok" if db_ok else "degraded",
        db="ok" if db_ok else "down",
        version=settings.app_version,
    )
