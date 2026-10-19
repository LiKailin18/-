"""文件访问路由（头像）。

为什么不用 StaticFiles：静态目录无法做归属校验，等于任何人都能猜路径下载。
所有文件访问都必须经过鉴权 + 路径穿越防护（app/utils/files.resolve_safe）。
"""

import re

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser
from app.core.exceptions import NotFound
from app.core.openapi import ERR_401, ERR_404
from app.utils import files

router = APIRouter(
    prefix="/files",
    tags=["文件"],
    responses={401: ERR_401, 404: ERR_404},
)

# 头像文件名形如：<uuid>_<8位hex>.<png|jpg|jpeg>
_AVATAR_NAME = re.compile(r"^[0-9a-f\-]{36}_[0-9a-f]{8}\.(png|jpg|jpeg)$")

_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@router.get("/avatars/{filename}", summary="获取头像")
async def get_avatar(filename: str, _current_user: CurrentUser) -> FileResponse:
    """登录用户可访问（头像不属于敏感数据，但也不做匿名公开）。"""
    if not _AVATAR_NAME.match(filename):
        raise NotFound("文件不存在")

    path = files.resolve_safe(f"avatars/{filename}")
    if not path.is_file():
        raise NotFound("文件不存在")

    suffix = path.suffix.lower()
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(suffix, "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=3600"},
    )
