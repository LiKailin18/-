"""在线笔记业务逻辑（功能 4）。

只做 CRUD + 搜索；不跨 service 调用 —— 校验资料归属时直接查 material 表，
保持各 service 只依赖自己的表（CLAUDE.md §5.1）。
"""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.models import Material, Note, utcnow
from app.schemas.note import NoteCreate, NoteUpdate
from app.utils.text import escape_like


async def _ensure_material_owned(
    db: AsyncSession, user_id: uuid.UUID, material_id: uuid.UUID
) -> None:
    """关联资料必须存在、属于本人、且未删除；否则统一 404。"""
    exists = await db.scalar(
        select(Material.id).where(
            Material.id == material_id,
            Material.user_id == user_id,
            Material.deleted_at.is_(None),
        )
    )
    if exists is None:
        raise NotFound("资料不存在")


async def create_note(db: AsyncSession, *, user_id: uuid.UUID, data: NoteCreate) -> Note:
    if data.material_id is not None:
        await _ensure_material_owned(db, user_id, data.material_id)

    note = Note(user_id=user_id, **data.model_dump())
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_notes(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    offset: int,
    limit: int,
    keyword: str | None = None,
    material_id: uuid.UUID | None = None,
    tag: str | None = None,
) -> tuple[list[Note], int]:
    conditions = [Note.user_id == user_id, Note.deleted_at.is_(None)]

    if keyword:
        pattern = f"%{escape_like(keyword)}%"
        # 标题与正文都搜（正文有 trgm 索引，见 docs/db.md §3.3）
        conditions.append(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
    if material_id:
        conditions.append(Note.material_id == material_id)
    if tag:
        conditions.append(Note.tags.contains([tag]))

    total = await db.scalar(select(func.count()).select_from(Note).where(*conditions))
    result = await db.execute(
        select(Note)
        .where(*conditions)
        .order_by(Note.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), int(total or 0)


async def get_owned(db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID) -> Note:
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == user_id,
            Note.deleted_at.is_(None),
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise NotFound("笔记不存在")
    return note


async def update_note(db: AsyncSession, note: Note, data: NoteUpdate) -> Note:
    changes = data.model_dump(exclude_unset=True)

    if changes.get("material_id") is not None:
        await _ensure_material_owned(db, note.user_id, changes["material_id"])

    for field, value in changes.items():
        setattr(note, field, value)

    note.updated_at = utcnow()
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, note: Note) -> None:
    note.deleted_at = utcnow()
    note.updated_at = utcnow()
    await db.commit()
