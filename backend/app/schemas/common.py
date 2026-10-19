"""通用响应模型。

分页结构固定为 {items, total, page, size}（契约 docs/api.md §1.2），
所有列表接口共用本模型，避免每个模块各写一份。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 20


class MessageOut(BaseModel):
    """只需要一句话反馈的接口（如重解析被接受）。"""

    message: str
