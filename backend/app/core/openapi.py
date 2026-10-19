"""OpenAPI 错误响应预设。

目的：让 Swagger 里**逐个接口**都能看到真实的错误契约（code 取值），
而不是只有 FastAPI 自动生成的 422。

用法：
    from app.core.openapi import ERR_401, ERR_404
    router = APIRouter(prefix="/xxx", responses={401: ERR_401, 403: ERR_403})
    @router.get("/{id}", responses={404: ERR_404})
"""

from app.schemas.error import ErrorOut


def error_response(description: str) -> dict:
    return {"model": ErrorOut, "description": description}


ERR_400 = error_response(
    "请求有误（SYS_400 / USER_004 / ADMIN_001 等，看 message）"
)
ERR_401 = error_response("未登录(AUTH_001) / 令牌过期(AUTH_002) / 令牌无效或已吊销(AUTH_003)")
ERR_403 = error_response("权限不足(AUTH_004) / 账号被禁用(USER_003) / 来源校验失败(AUTH_005)")
ERR_404 = error_response("资源不存在**或不属于当前用户**（故意不区分，防 ID 枚举）")
ERR_409 = error_response(
    "冲突：用户名已存在(USER_001) / 邮箱已存在(USER_002) / 任务已生成(PLAN_001)"
)
ERR_413 = error_response("文件超过大小限制（MAT_002）")
ERR_429 = error_response("超出调用配额（AI_004）")
ERR_502 = error_response("上游模型异常（AI_001 / AI_002）")
ERR_503 = error_response("功能已暂停（SYS_503）")
ERR_504 = error_response("调用超时（AI_003）")
