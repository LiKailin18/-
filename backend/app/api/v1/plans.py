"""学习计划接口（契约：docs/api.md §7）—— 功能 5。"""

import uuid

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession, PageParams
from app.core.openapi import ERR_400, ERR_401, ERR_403, ERR_404, ERR_409
from app.models import Material, StudyPlan
from app.schemas.common import Page
from app.schemas.plan import (
    GenerateTasksIn,
    GenerateTasksOut,
    MaterialBrief,
    PlanCreate,
    PlanDetailOut,
    PlanOut,
    PlanProgress,
    PlanUpdate,
)
from app.services import plan_service

router = APIRouter(
    prefix="/plans",
    tags=["学习计划"],
    responses={
        status.HTTP_401_UNAUTHORIZED: ERR_401,
        status.HTTP_403_FORBIDDEN: ERR_403,
        status.HTTP_404_NOT_FOUND: ERR_404,
    },
)


def _out(plan: StudyPlan, progress: PlanProgress) -> PlanOut:
    return PlanOut.model_validate(plan).model_copy(update={"progress": progress})


@router.post(
    "", summary="新建计划", status_code=status.HTTP_201_CREATED, response_model=PlanOut
)
async def create_plan(payload: PlanCreate, current_user: CurrentUser, db: DbSession) -> PlanOut:
    plan = await plan_service.create_plan(db, user_id=current_user.id, data=payload)
    return _out(plan, PlanProgress())


@router.get("", summary="计划列表", response_model=Page[PlanOut])
async def list_plans(
    current_user: CurrentUser,
    db: DbSession,
    page: PageParams,
    status_filter: str | None = Query(default=None, alias="status", description="按状态过滤"),
) -> Page[PlanOut]:
    plans, total, progress = await plan_service.list_plans(
        db,
        user_id=current_user.id,
        offset=page.offset,
        limit=page.size,
        status=status_filter,
    )
    return Page[PlanOut](
        items=[_out(plan, progress.get(plan.id, PlanProgress())) for plan in plans],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.get("/{plan_id}", summary="计划详情", response_model=PlanDetailOut)
async def get_plan(plan_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> PlanDetailOut:
    plan = await plan_service.get_owned(db, current_user.id, plan_id)
    progress = await plan_service.progress_for(db, plan.id)

    materials: list[MaterialBrief] = []
    if plan.material_ids:
        from sqlalchemy import select

        result = await db.execute(
            select(Material).where(
                Material.id.in_(plan.material_ids),
                Material.user_id == current_user.id,
                Material.deleted_at.is_(None),
            )
        )
        materials = [MaterialBrief.model_validate(item) for item in result.scalars().all()]

    return PlanDetailOut(
        **PlanOut.model_validate(plan).model_dump(exclude={"progress"}),
        progress=progress,
        materials=materials,
    )


@router.patch(
    "/{plan_id}",
    summary="修改计划",
    response_model=PlanOut,
    responses={status.HTTP_400_BAD_REQUEST: ERR_400},
)
async def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> PlanOut:
    plan = await plan_service.get_owned(db, current_user.id, plan_id)
    updated = await plan_service.update_plan(db, plan, payload)
    return _out(updated, await plan_service.progress_for(db, updated.id))


@router.delete("/{plan_id}", summary="删除计划", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    plan = await plan_service.get_owned(db, current_user.id, plan_id)
    await plan_service.delete_plan(db, plan)


@router.post(
    "/{plan_id}/generate-tasks",
    summary="生成每日任务",
    status_code=status.HTTP_201_CREATED,
    response_model=GenerateTasksOut,
    responses={status.HTTP_400_BAD_REQUEST: ERR_400, status.HTTP_409_CONFLICT: ERR_409},
)
async def generate_tasks(
    plan_id: uuid.UUID,
    payload: GenerateTasksIn,
    current_user: CurrentUser,
    db: DbSession,
) -> GenerateTasksOut:
    """幂等：区间内已存在的日期会计入 skipped；全部已存在则返回 409 PLAN_001。"""
    plan = await plan_service.get_owned(db, current_user.id, plan_id)
    return await plan_service.generate_tasks(db, plan, overwrite=payload.overwrite)
