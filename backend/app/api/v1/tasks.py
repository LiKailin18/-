"""学习任务接口（契约：docs/api.md §8）—— 功能 6。"""

import uuid
from datetime import date

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession, PageParams
from app.core.openapi import ERR_400, ERR_401, ERR_403, ERR_404
from app.schemas.common import Page
from app.schemas.task import TaskCompleteIn, TaskCompleteOut, TaskCreate, TaskOut, TaskUpdate
from app.services import task_service

router = APIRouter(
    prefix="/tasks",
    tags=["学习任务"],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)


@router.get("", summary="任务列表", response_model=Page[TaskOut])
async def list_tasks(
    current_user: CurrentUser,
    db: DbSession,
    page: PageParams,
    plan_id: uuid.UUID | None = None,
    plan_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> Page[TaskOut]:
    items, total = await task_service.list_tasks(
        db,
        user_id=current_user.id,
        offset=page.offset,
        limit=page.size,
        plan_id=plan_id,
        plan_date=plan_date,
        date_from=date_from,
        date_to=date_to,
        status=status_filter,
    )
    return Page[TaskOut](
        items=[TaskOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.post(
    "", summary="手工新建任务", status_code=status.HTTP_201_CREATED, response_model=TaskOut
)
async def create_task(payload: TaskCreate, current_user: CurrentUser, db: DbSession) -> TaskOut:
    task = await task_service.create_task(db, user_id=current_user.id, data=payload)
    return TaskOut.model_validate(task)


@router.patch(
    "/{task_id}",
    summary="修改任务",
    response_model=TaskOut,
    responses={status.HTTP_400_BAD_REQUEST: ERR_400},
)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> TaskOut:
    task = await task_service.get_owned(db, current_user.id, task_id)
    updated = await task_service.update_task(db, task, payload)
    return TaskOut.model_validate(updated)


@router.post(
    "/{task_id}/complete",
    summary="完成任务（同时记录学习时长）",
    response_model=TaskCompleteOut,
    responses={status.HTTP_400_BAD_REQUEST: ERR_400},
)
async def complete_task(
    task_id: uuid.UUID,
    payload: TaskCompleteIn,
    current_user: CurrentUser,
    db: DbSession,
) -> TaskCompleteOut:
    """原子操作：任务状态与学习记录在同一事务内提交。"""
    task = await task_service.get_owned(db, current_user.id, task_id)
    updated, record = await task_service.complete_task(db, task, payload)
    return TaskCompleteOut(
        task=TaskOut.model_validate(updated),
        study_record_id=record.id if record else None,
    )


@router.delete("/{task_id}", summary="删除任务", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    task = await task_service.get_owned(db, current_user.id, task_id)
    await task_service.delete_task(db, task)
