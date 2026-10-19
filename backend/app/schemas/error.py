"""统一错误体模型（契约：docs/api.md §1.3）。

用途有两个：
1. 作为 Swagger/OpenAPI 的响应模型 —— 让文档展示的 422/4xx 形状与**实际返回**一致
   （FastAPI 默认会把 422 渲染成 {"detail": [...]}，那是框架默认体，不是我们的契约）
2. 前端生成类型时能拿到准确的错误结构

真正的响应由 app/core/exceptions.py 里的处理器产出，本模型只用于文档。
"""

from typing import Any

from pydantic import BaseModel, Field


class ErrorOut(BaseModel):
    code: str = Field(description="业务错误码，如 SYS_422 / AUTH_003 / MAT_003")
    message: str = Field(description="可直接展示给用户的中文文案")
    detail: Any | None = Field(default=None, description="可选的字段级详情或上下文")
