"""学习记录接口（契约：docs/api.md §9）—— 功能 12。"""

import uuid
from datetime import date

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession, PageParams
from app.core.openapi import ERR_401, ERR_403, ERR_404
from app.schemas.common import Page
from app.schemas.record import RecordCreate, RecordOut, RecordUpdate
from app.services import record_service

router = APIRouter(
    prefix="/study-records",
    tags=["学习记录"],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)


@router.post(
    "", summary="新建学习记录", status_code=status.HTTP_201_CREATED, response_model=RecordOut
)
async def create_record(
    payload: RecordCreate, current_user: CurrentUser, db: DbSession
) -> RecordOut:
    record = await record_service.create_record(db, user_id=current_user.id, data=payload)
    return RecordOut.model_validate(record)


@router.get("", summary="学习记录列表", response_model=Page[RecordOut])
async def list_records(
    current_user: CurrentUser,
    db: DbSession,
    page: PageParams,
    date_from: date | None = None,
    date_to: date | None = None,
    record_type: str | None = Query(default=None, alias="type"),
    plan_id: uuid.UUID | None = None,
) -> Page[RecordOut]:
    items, total = await record_service.list_records(
        db,
        user_id=current_user.id,
        offset=page.offset,
        limit=page.size,
        date_from=date_from,
        date_to=date_to,
        record_type=record_type,
        plan_id=plan_id,
    )
    return Page[RecordOut](
        items=[RecordOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.patch("/{record_id}", summary="修改学习记录", response_model=RecordOut)
async def update_record(
    record_id: uuid.UUID,
    payload: RecordUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> RecordOut:
    record = await record_service.get_owned(db, current_user.id, record_id)
    updated = await record_service.update_record(db, record, payload)
    return RecordOut.model_validate(updated)


@router.delete(
    "/{record_id}", summary="删除学习记录", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_record(record_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    record = await record_service.get_owned(db, current_user.id, record_id)
    await record_service.delete_record(db, record)
