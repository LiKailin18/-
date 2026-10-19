"""功能 13 管理端路由聚合（契约：docs/api.md §16）。

挂载方式：`api_v1_router.include_router(admin.admin_router)` → 全部在 `/api/v1/admin` 下。

两条纪律（契约 §16 开头）：
1. 所有写操作必须写 admin_audit_log，且与业务变更**同事务**提交
2. 管理端**不提供任何 AI 生成类接口**（成本与内容合规上的边界）
"""

from fastapi import APIRouter, status

from app.api.v1.admin import ai_usage, audit, content, settings, stats, users
from app.core.openapi import ERR_400, ERR_401, ERR_403, ERR_404

admin_router = APIRouter(
    prefix="/admin",
    tags=["功能 13 · 管理端"],
    responses={
        status.HTTP_400_BAD_REQUEST: ERR_400,
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        # 非管理员访问管理端 → 403 AUTH_004（用户端越权才是 404）
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)

admin_router.include_router(stats.router)
admin_router.include_router(ai_usage.router)
admin_router.include_router(users.router)
admin_router.include_router(content.router)
admin_router.include_router(settings.router)
admin_router.include_router(audit.router)
