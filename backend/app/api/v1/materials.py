"""学习资料接口（契约：docs/api.md §5）—— 功能 3。

路由只做编排：参数解析、状态码、把解析任务丢给 BackgroundTasks。
文件校验、落盘、解析、状态机全在 utils / services 里。
"""

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser, DbSession, PageParams
from app.core.exceptions import NotFound
from app.core.openapi import ERR_400, ERR_401, ERR_403, ERR_404, ERR_413
from app.schemas.common import Page
from app.schemas.material import MaterialOut, MaterialTextOut, MaterialUpdate
from app.services import material_service
from app.utils import files
from app.utils import text as text_utils

router = APIRouter(
    prefix="/materials",
    tags=["学习资料"],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)

MAX_TAGS = 20


@router.post(
    "",
    summary="上传学习资料",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MaterialOut,
    responses={
        status.HTTP_400_BAD_REQUEST: ERR_400,
        status.HTTP_413_CONTENT_TOO_LARGE: ERR_413,
    },
)
async def upload_material(
    background: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(description="PDF 或 DOCX，大小受 MAX_UPLOAD_MB 限制")],
    title: Annotated[str | None, Form(description="缺省取文件名")] = None,
    subject: Annotated[str | None, Form(description="科目，用于统计")] = None,
    tags: Annotated[str | None, Form(description="逗号分隔，如：高数,极限")] = None,
) -> MaterialOut:
    """返回 202：解析在后台进行，前端轮询详情直到 parse_status 变为终态。"""
    material = await material_service.create_material(
        db,
        user_id=current_user.id,
        upload=file,
        title=title,
        subject=subject,
        tags=text_utils.parse_tag_string(tags),
    )
    background.add_task(material_service.parse_material, material.id)
    return MaterialOut.model_validate(material)


@router.get("", summary="资料列表", response_model=Page[MaterialOut])
async def list_materials(
    current_user: CurrentUser,
    db: DbSession,
    page: PageParams,
    keyword: Annotated[str | None, Query(description="模糊匹配标题")] = None,
    subject: Annotated[str | None, Query(description="按科目过滤")] = None,
    parse_status: Annotated[str | None, Query(description="按解析状态过滤")] = None,
) -> Page[MaterialOut]:
    items, total = await material_service.list_materials(
        db,
        user_id=current_user.id,
        offset=page.offset,
        limit=page.size,
        keyword=keyword,
        subject=subject,
        parse_status=parse_status,
    )
    return Page[MaterialOut](
        items=[MaterialOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.get("/{material_id}", summary="资料详情", response_model=MaterialOut)
async def get_material(
    material_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> MaterialOut:
    material = await material_service.get_owned(db, current_user.id, material_id)
    return MaterialOut.model_validate(material)


@router.patch("/{material_id}", summary="修改资料", response_model=MaterialOut)
async def update_material(
    material_id: uuid.UUID,
    payload: MaterialUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> MaterialOut:
    material = await material_service.get_owned(db, current_user.id, material_id)
    updated = await material_service.update_material(db, material, payload)
    return MaterialOut.model_validate(updated)


@router.delete(
    "/{material_id}", summary="删除资料", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_material(
    material_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> None:
    material = await material_service.get_owned(db, current_user.id, material_id)
    await material_service.delete_material(db, material)


@router.get("/{material_id}/download", summary="下载原文件")
async def download_material(
    material_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> FileResponse:
    """必须校验归属后再返回文件 —— 绝不能把 storage 目录当静态目录暴露。"""
    material = await material_service.get_owned(db, current_user.id, material_id)
    path = files.resolve_safe(material.file_path)
    if not path.is_file():
        raise NotFound("文件已丢失")

    return FileResponse(
        path,
        media_type=material.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(material.file_name)}"
        },
    )


@router.get("/{material_id}/text", summary="分片读取正文", response_model=MaterialTextOut)
async def read_material_text(
    material_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    offset: Annotated[int, Query(ge=0, description="字符偏移")] = 0,
    limit: Annotated[int, Query(ge=1, le=8000, description="字符数，上限 8000")] = 4000,
) -> MaterialTextOut:
    """offset/limit 是**字符**偏移；limit 上限 8000。"""
    safe_limit = max(1, min(limit, 8000))
    safe_offset = max(0, offset)
    return await material_service.read_text_chunk(
        db,
        user_id=current_user.id,
        material_id=material_id,
        offset=safe_offset,
        limit=safe_limit,
    )


@router.post(
    "/{material_id}/reparse",
    summary="重新解析",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MaterialOut,
    responses={status.HTTP_400_BAD_REQUEST: ERR_400},
)
async def reparse_material(
    material_id: uuid.UUID,
    background: BackgroundTasks,
    current_user: CurrentUser,
    db: DbSession,
) -> MaterialOut:
    material = await material_service.get_owned(db, current_user.id, material_id)
    updated = await material_service.reparse(db, material)
    background.add_task(material_service.parse_material, updated.id)
    return MaterialOut.model_validate(updated)
