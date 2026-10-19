"""管理端内容管理（功能 13.3；契约：docs/api.md §16.3）。

写操作把「业务变更 + 审计日志」放在同一个事务里提交（CLAUDE.md 的审计纪律），
资料下架还会删磁盘文件 —— 删文件放在 commit 之后（文件删不掉也不该回滚数据）。
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Query, Request, status

from app.core.deps import CurrentAdmin, DbSession, PageParams
from app.core.openapi import ERR_404
from app.models import Material, Note, Quiz
from app.schemas.admin import (
    AdminMaterialItemOut,
    AdminMaterialPage,
    AdminNoteItemOut,
    AdminNotePage,
    AdminQuizItemOut,
    AdminQuizPage,
)
from app.services import admin_content_service, audit_service
from app.utils import files

router = APIRouter(tags=["管理端 · 内容管理"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


# ------------------------------------------------------------------ 资料


@router.get("/materials", summary="全站资料", response_model=AdminMaterialPage)
async def list_materials(
    _admin: CurrentAdmin,
    db: DbSession,
    page: PageParams,
    keyword: str | None = None,
    user_id: uuid.UUID | None = None,
    parse_status: str | None = Query(default=None, description="pending/parsing/success/failed"),
    file_ext: str | None = Query(default=None, description=".pdf / .docx"),
) -> AdminMaterialPage:
    items, total = await admin_content_service.list_materials(
        db,
        offset=page.offset,
        limit=page.size,
        keyword=keyword,
        user_id=user_id,
        parse_status=parse_status,
        file_ext=file_ext,
    )
    return AdminMaterialPage(
        items=[AdminMaterialItemOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.delete(
    "/materials/{material_id}",
    summary="下架资料（软删除 + 删文件）",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_404_NOT_FOUND: ERR_404},
)
async def delete_material(
    material_id: uuid.UUID,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
) -> None:
    ip, user_agent = _client_meta(request)
    material = await admin_content_service.soft_delete(db, Material, material_id, "资料")
    audit_service.write_log(
        db,
        admin_id=admin.id,
        action=audit_service.ACTION_MATERIAL_DELETE,
        target_type="material",
        target_id=material.id,
        detail={"title": material.title, "owner_id": str(material.user_id)},
        ip=ip,
        user_agent=user_agent,
    )
    await db.commit()

    # 文件删除放在事务之后：即使删文件失败，数据也已经一致地下架了
    files.delete_file(material.file_path)


@router.post(
    "/materials/{material_id}/reparse",
    summary="重新解析资料（异步）",
    status_code=status.HTTP_202_ACCEPTED,
    responses={status.HTTP_404_NOT_FOUND: ERR_404},
)
async def reparse_material(
    material_id: uuid.UUID,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
    background: BackgroundTasks,
) -> dict:
    ip, user_agent = _client_meta(request)
    material = await admin_content_service.mark_reparse(db, material_id)
    audit_service.write_log(
        db,
        admin_id=admin.id,
        action=audit_service.ACTION_MATERIAL_REPARSE,
        target_type="material",
        target_id=material.id,
        detail={"title": material.title, "owner_id": str(material.user_id)},
        ip=ip,
        user_agent=user_agent,
    )
    await db.commit()

    from app.services import material_service

    background.add_task(material_service.parse_material, material.id)
    return {"material_id": str(material.id), "status": "pending", "note": "已重新排队解析"}


# ------------------------------------------------------------------ 笔记


@router.get("/notes", summary="全站笔记（只给摘要）", response_model=AdminNotePage)
async def list_notes(
    _admin: CurrentAdmin,
    db: DbSession,
    page: PageParams,
    keyword: str | None = None,
    user_id: uuid.UUID | None = None,
) -> AdminNotePage:
    items, total = await admin_content_service.list_notes(
        db, offset=page.offset, limit=page.size, keyword=keyword, user_id=user_id
    )
    return AdminNotePage(
        items=[AdminNoteItemOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.delete(
    "/notes/{note_id}",
    summary="删除笔记",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_404_NOT_FOUND: ERR_404},
)
async def delete_note(
    note_id: uuid.UUID, admin: CurrentAdmin, db: DbSession, request: Request
) -> None:
    ip, user_agent = _client_meta(request)
    note = await admin_content_service.soft_delete(db, Note, note_id, "笔记")
    audit_service.write_log(
        db,
        admin_id=admin.id,
        action=audit_service.ACTION_NOTE_DELETE,
        target_type="note",
        target_id=note.id,
        detail={"title": note.title, "owner_id": str(note.user_id)},
        ip=ip,
        user_agent=user_agent,
    )
    await db.commit()


# ------------------------------------------------------------------ 测试题


@router.get("/quizzes", summary="全站测试题（不含题目与答案）", response_model=AdminQuizPage)
async def list_quizzes(
    _admin: CurrentAdmin,
    db: DbSession,
    page: PageParams,
    user_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
) -> AdminQuizPage:
    items, total = await admin_content_service.list_quizzes(
        db,
        offset=page.offset,
        limit=page.size,
        user_id=user_id,
        material_id=material_id,
    )
    return AdminQuizPage(
        items=[AdminQuizItemOut.model_validate(item) for item in items],
        total=total,
        page=page.page,
        size=page.size,
    )


@router.delete(
    "/quizzes/{quiz_id}",
    summary="下架测试题（历史答卷保留）",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_404_NOT_FOUND: ERR_404},
)
async def delete_quiz(
    quiz_id: uuid.UUID, admin: CurrentAdmin, db: DbSession, request: Request
) -> None:
    """下架只影响「还能不能继续做」；`quiz_attempt` 保留并继续计入统计（论文的设计取舍之一）。"""
    ip, user_agent = _client_meta(request)
    quiz = await admin_content_service.soft_delete(db, Quiz, quiz_id, "测试题")
    audit_service.write_log(
        db,
        admin_id=admin.id,
        action=audit_service.ACTION_QUIZ_DELETE,
        target_type="quiz",
        target_id=quiz.id,
        detail={"title": quiz.title, "owner_id": str(quiz.user_id)},
        ip=ip,
        user_agent=user_agent,
    )
    await db.commit()
