"""管理端内容管理（功能 13.3；契约：docs/api.md §16.3）。

三条边界：

1. **列表不返回大字段**：资料不给 `extracted_text`、笔记只给 `excerpt`、题目不给 `questions`
   （管理端也没有「看答案」的需求，少一个泄露面是一个）
2. **下架 = 软删除**：`deleted_at` 置位，历史数据（答卷、统计）不受影响
3. **审计与变更同事务**：本模块的写操作只 `flush` 不 `commit`，
   由路由层把审计日志一起提交（与用户端 service 自己 commit 的写法不同，原因在此）
"""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.models import AppUser, Material, Note, Quiz, utcnow

NOTE_EXCERPT_CHARS = 120


def _owner_filter(model, user_id: uuid.UUID | None):
    return [model.user_id == user_id] if user_id else []


async def list_materials(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
    keyword: str | None = None,
    user_id: uuid.UUID | None = None,
    parse_status: str | None = None,
    file_ext: str | None = None,
) -> tuple[list[dict], int]:
    conditions = [Material.deleted_at.is_(None), *_owner_filter(Material, user_id)]
    if keyword:
        conditions.append(Material.title.ilike(f"%{keyword.strip()}%"))
    if parse_status:
        conditions.append(Material.parse_status == parse_status)
    if file_ext:
        conditions.append(Material.file_ext == file_ext)

    total = await db.scalar(select(func.count()).select_from(Material).where(*conditions))
    rows = (
        await db.execute(
            select(Material, AppUser.username)
            .join(AppUser, AppUser.id == Material.user_id, isouter=True)
            .where(*conditions)
            .order_by(Material.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [
        {
            "id": row.Material.id,
            "title": row.Material.title,
            "subject": row.Material.subject,
            "file_ext": row.Material.file_ext,
            "size_bytes": row.Material.size_bytes,
            "parse_status": row.Material.parse_status,
            "char_count": row.Material.char_count,
            "created_at": row.Material.created_at,
            "owner": {"id": row.Material.user_id, "username": row.username or "（已删除）"},
        }
        for row in rows
    ]
    return items, int(total or 0)


async def list_notes(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
    keyword: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[list[dict], int]:
    conditions = [Note.deleted_at.is_(None), *_owner_filter(Note, user_id)]
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))

    total = await db.scalar(select(func.count()).select_from(Note).where(*conditions))
    rows = (
        await db.execute(
            select(Note, AppUser.username)
            .join(AppUser, AppUser.id == Note.user_id, isouter=True)
            .where(*conditions)
            .order_by(Note.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [
        {
            "id": row.Note.id,
            "title": row.Note.title,
            # 契约 §16.3：只给摘要，不返回完整正文
            "excerpt": (row.Note.content or "")[:NOTE_EXCERPT_CHARS],
            "tags": row.Note.tags,
            "material_id": row.Note.material_id,
            "created_at": row.Note.created_at,
            "updated_at": row.Note.updated_at,
            "owner": {"id": row.Note.user_id, "username": row.username or "（已删除）"},
        }
        for row in rows
    ]
    return items, int(total or 0)


async def list_quizzes(
    db: AsyncSession,
    *,
    offset: int,
    limit: int,
    user_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
) -> tuple[list[dict], int]:
    conditions = [Quiz.deleted_at.is_(None), *_owner_filter(Quiz, user_id)]
    if material_id:
        conditions.append(Quiz.material_id == material_id)

    total = await db.scalar(select(func.count()).select_from(Quiz).where(*conditions))
    rows = (
        await db.execute(
            select(Quiz, AppUser.username)
            .join(AppUser, AppUser.id == Quiz.user_id, isouter=True)
            .where(*conditions)
            .order_by(Quiz.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [
        {
            "id": row.Quiz.id,
            "title": row.Quiz.title,
            "question_count": row.Quiz.question_count,
            "types": row.Quiz.types,
            "difficulty": row.Quiz.difficulty,
            "material_id": row.Quiz.material_id,
            "created_at": row.Quiz.created_at,
            # 契约：管理端列表不含题目与答案
            "owner": {"id": row.Quiz.user_id, "username": row.username or "（已删除）"},
        }
        for row in rows
    ]
    return items, int(total or 0)


async def _get_row(db: AsyncSession, model: Any, row_id: uuid.UUID, label: str):
    row = await db.get(model, row_id)
    if row is None or getattr(row, "deleted_at", None) is not None:
        raise NotFound(f"{label}不存在")
    return row


async def soft_delete(db: AsyncSession, model: Any, row_id: uuid.UUID, label: str):
    """软删除（只 flush，不 commit —— 审计要一起提交）。"""
    row = await _get_row(db, model, row_id, label)
    row.deleted_at = utcnow()
    row.updated_at = utcnow()
    db.add(row)
    await db.flush()
    return row


async def mark_reparse(db: AsyncSession, material_id: uuid.UUID) -> Material:
    """把资料置回 pending（只 flush）；返回后由路由层提交并丢给 BackgroundTasks。"""
    material = await _get_row(db, Material, material_id, "资料")
    material.parse_status = "pending"
    material.parse_error = None
    material.updated_at = utcnow()
    db.add(material)
    await db.flush()
    return material
