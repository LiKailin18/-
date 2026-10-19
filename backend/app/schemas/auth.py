"""认证相关的请求/响应模型（契约：docs/api.md §3）。"""

from pydantic import BaseModel


class TokenOut(BaseModel):
    """登录 / 刷新的出参。

    `role` 仅供前端决定是否显示管理端入口；服务端鉴权一律读库判定（CLAUDE.md §4）。
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
