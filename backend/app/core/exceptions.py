"""业务异常与统一错误体。

约定（docs/api.md §1.3 / CLAUDE.md §7）：
- 错误响应固定为 `{code, message, detail}`
- `message` 是**可直接展示给用户的中文文案**，前端不要自己拼文案
- 代码里不抛 HTTPException，一律抛本模块的 AppError 子类（services 层不认识 HTTP）

错误码与状态码的对应关系必须与 docs/api.md §1.4 一致。
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """业务异常基类：子类只需声明 status_code / code / message。"""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "SYS_400"
    message: str = "请求有误"

    def __init__(
        self,
        message: str | None = None,
        detail: Any = None,
        *,
        code: str | None = None,
    ) -> None:
        if message:
            self.message = message
        if code:
            self.code = code
        self.detail = detail
        super().__init__(self.message)


# --------------------------------------------------------------------- 认证与权限


class Unauthorized(AppError):
    """未提供凭证。"""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTH_001"
    message = "未登录或缺少访问令牌"


class TokenExpired(AppError):
    """access token 过期 —— 前端**只对这一个码**触发刷新。"""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTH_002"
    message = "登录已过期，请重新登录"


class InvalidToken(AppError):
    """凭证无效或已被吊销（含 token_version 变更导致的集体失效）。"""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTH_003"
    message = "凭证无效或已被吊销"


class InvalidCredentials(AppError):
    """登录失败。message 固定，不区分「用户不存在」与「密码错误」。"""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTH_003"
    message = "用户名或密码错误"


class Forbidden(AppError):
    """已登录但角色不足（管理端接口）。"""

    status_code = status.HTTP_403_FORBIDDEN
    code = "AUTH_004"
    message = "权限不足"


class CsrfRejected(AppError):
    """Cookie 凭证接口的 Origin 校验失败。"""

    status_code = status.HTTP_403_FORBIDDEN
    code = "AUTH_005"
    message = "请求来源不被允许"


class AccountDisabled(AppError):
    """账号被管理员禁用。"""

    status_code = status.HTTP_403_FORBIDDEN
    code = "USER_003"
    message = "账号已被禁用"


# --------------------------------------------------------------------- 用户


class UsernameTaken(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "USER_001"
    message = "用户名已存在"


class EmailTaken(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "USER_002"
    message = "邮箱已存在"


class WrongOldPassword(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "USER_004"
    message = "原密码不正确"


# --------------------------------------------------------------------- 通用


class NotFound(AppError):
    """资源不存在**或不属于当前用户** —— 故意不区分，防 ID 枚举。"""

    status_code = status.HTTP_404_NOT_FOUND
    code = "SYS_404"
    message = "资源不存在"


class BadRequest(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "SYS_400"
    message = "请求有误"


class PlanTasksExist(AppError):
    """该计划区间的任务已全部生成（409 PLAN_001）。"""

    status_code = status.HTTP_409_CONFLICT
    code = "PLAN_001"
    message = "该计划区间的任务已全部生成"


# --------------------------------------------------------------------- 文件解析


class MaterialNotParsed(AppError):
    """资料还没解析完就去做 AI 处理（422 MAT_001）。"""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "MAT_001"
    message = "该资料尚未解析完成，请稍后重试"


class ScannedUnsupported(AppError):
    """扫描版没有文本层（422 MAT_004）。"""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "MAT_004"
    message = "该文件为扫描版，暂不支持识别"


# --------------------------------------------------------------------- AI


class AiNotConfigured(AppError):
    """没配置 LLM_API_KEY —— 不是错误，是「功能还没开」。"""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SYS_503"
    message = "AI 功能未配置：请在后端环境变量里设置 LLM_API_KEY"


class AiOutputInvalid(AppError):
    """结构化输出校验失败且重试后仍失败（502 AI_001）。"""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "AI_001"
    message = "AI 输出格式不正确，请重试"


class AiUpstreamError(AppError):
    """上游模型 5xx / 网络错误（502 AI_002）。"""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "AI_002"
    message = "AI 服务暂时不可用，请稍后重试"


class AiTimeout(AppError):
    """整轮 agent 循环超时（504 AI_003）—— 注意不是单次请求超时。"""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "AI_003"
    message = "AI 响应超时，请稍后重试或缩小问题范围"


class AiQuotaExceeded(AppError):
    """超出当日配额（429 AI_004）。"""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "AI_004"
    message = "今日 AI 调用次数已用完，请明天再试"


class AiStepsExceeded(AppError):
    """agent 步数超限（400 AI_005）。"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "AI_005"
    message = "问题过于复杂，请缩小范围后重试"


class FeatureDisabled(AppError):
    """功能被管理员关闭（如 ai.enabled=false、register.allow=false）。"""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SYS_503"
    message = "该功能已暂停使用"


# --------------------------------------------------------------------- 处理器


def _error_response(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "detail": jsonable_encoder(exc.detail),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """把三类异常统一成契约约定的错误体。"""

    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # detail 给字段级错误，前端可直接定位到表单项
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "code": "SYS_422",
                "message": "请求参数校验失败",
                "detail": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # FastAPI/Starlette 自己抛出的（如 404 路由未匹配）也要包成统一格式
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": f"SYS_{exc.status_code}",
                "message": str(exc.detail),
                "detail": None,
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # 原始异常只进日志，不外传（契约要求不泄露堆栈）
        logger.exception("未处理异常: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "SYS_500", "message": "服务内部错误", "detail": None},
        )
