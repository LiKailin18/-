"""健康检查响应模型（契约：docs/api.md §1.6）。"""

from typing import Literal

from pydantic import BaseModel


class HealthOut(BaseModel):
    """健康检查响应。字段与契约严格一一对应，新增字段必须先改契约文档。"""

    status: Literal["ok", "degraded"] = "ok"
    db: Literal["ok", "down"] = "ok"
    version: str
