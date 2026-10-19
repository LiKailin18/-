"""在线笔记接口（契约：docs/api.md §6）—— 功能 4。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession, PageParams
from app.core.openapi import ERR_401, ERR_403, ERR_404
from app.schemas.common import Page
from app.schemas.note import NoteCreate, NoteListItem, NoteOut, NoteUpdate
from app.services import note_service
from app.utils.text import make_excerpt

router = APIRouter(
    prefix="/notes",
    tags=["在线笔记"],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)


@router.post(
    "", summary="新建笔记", status_code=status.HTTP_201_CREATED, response_model=NoteOut
)
async def create_note(payload: NoteCreate, current_user: CurrentUser, db: DbSession) -> NoteOut:
    note = await note_service.create_note(db, user_id=current_user.id, data=payload)
    return NoteOut.model_validate(note)


@router.get("", summary="笔记列表", response_model=Page[NoteListItem])
async def list_notes(
    current_user: CurrentUser,
    db: DbSession,
    page: PageParams,
    keyword: Annotated[str | None, Query(description="在标题与正文中模糊搜索")] = None,
    material_id: Annotated[uuid.UUID | None, Query(description="按关联资料过滤")] = None,
    tag: Annotated[str | None, Query(description="按标签过滤")] = None,
) -> Page[NoteListItem]:
    """列表**不返回正文**，只给 120 字摘要（避免列表接口返回大字段）。"""
    notes, total = await note_service.list_notes(
        db,
        user_id=current_user.id,
        offset=page.offset,
        limit=page.size,
        keyword=keyword,
        material_id=material_id,
        tag=tag,
    )
    return Page[NoteListItem](
        items=[
            NoteListItem(
                id=note.id,
                title=note.title,
                excerpt=make_excerpt(note.content),
                tags=note.tags,
                material_id=note.material_id,
                updated_at=note.updated_at,
            )
            for note in notes
        ],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.get("/{note_id}", summary="笔记详情", response_model=NoteOut)
async def get_note(note_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> NoteOut:
    note = await note_service.get_owned(db, current_user.id, note_id)
    return NoteOut.model_validate(note)


@router.patch("/{note_id}", summary="修改笔记", response_model=NoteOut)
async def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteOut:
    note = await note_service.get_owned(db, current_user.id, note_id)
    updated = await note_service.update_note(db, note, payload)
    return NoteOut.model_validate(updated)


@router.delete("/{note_id}", summary="删除笔记", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    note = await note_service.get_owned(db, current_user.id, note_id)
    await note_service.delete_note(db, note)
