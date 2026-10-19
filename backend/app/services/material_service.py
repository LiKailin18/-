"""学习资料业务逻辑（功能 3）。

分工（CLAUDE.md §5.1）：
- 校验与落盘 → app/utils/files
- 解析 → app/utils/doc_parser（CPU 密集，后台任务里走线程池）
- 本模块只负责业务规则、事务与状态机
"""

import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import BadRequest, NotFound
from app.db.engine import SessionLocal
from app.models import Material, utcnow
from app.schemas.material import MaterialTextOut, MaterialUpdate
from app.services import setting_service
from app.utils import doc_parser, files
from app.utils import text as text_utils

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- 查询


async def get_owned(db: AsyncSession, user_id: uuid.UUID, material_id: uuid.UUID) -> Material:
    """按「本人 + 未删除」查询。

    不存在与不属于本人一律 NotFound（SYS_404），防 ID 枚举（CLAUDE.md §4）。
    """
    result = await db.execute(
        select(Material).where(
            Material.id == material_id,
            Material.user_id == user_id,
            Material.deleted_at.is_(None),
        )
    )
    material = result.scalar_one_or_none()
    if material is None:
        raise NotFound("资料不存在")
    return material


async def list_materials(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    offset: int,
    limit: int,
    keyword: str | None = None,
    subject: str | None = None,
    parse_status: str | None = None,
) -> tuple[list[Material], int]:
    conditions = [Material.user_id == user_id, Material.deleted_at.is_(None)]
    if keyword:
        conditions.append(
            Material.title.ilike(f"%{text_utils.escape_like(keyword)}%", escape="\\")
        )
    if subject:
        conditions.append(Material.subject == subject)
    if parse_status:
        conditions.append(Material.parse_status == parse_status)

    total = await db.scalar(select(func.count()).select_from(Material).where(*conditions))
    result = await db.execute(
        select(Material)
        .where(*conditions)
        .order_by(Material.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), int(total or 0)


# --------------------------------------------------------------------- 检索（供 AI 工具调用）


async def search_materials(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    keyword: str,
    limit: int = 3,
    window: int = 300,
) -> list[dict]:
    """在本人**已解析成功**的资料正文里检索关键词，返回带上下文的片段。

    与文档里的检索约定一致（docs/agent-tools.md §3.2）：
    命中位置前后各取 window 个字符，单条片段硬截断 600 字符。
    """
    pattern = f"%{text_utils.escape_like(keyword)}%"
    result = await db.execute(
        select(Material.id, Material.title, Material.extracted_text)
        .where(
            Material.user_id == user_id,
            Material.deleted_at.is_(None),
            Material.parse_status == "success",
            Material.extracted_text.ilike(pattern, escape="\\"),
        )
        .limit(limit)
    )

    hits: list[dict] = []
    for material_id, title, content in result:
        if not content:
            continue
        position = content.lower().find(keyword.lower())
        if position < 0:
            continue
        start = max(0, position - window)
        end = min(len(content), position + window)
        hits.append(
            {
                "material_id": str(material_id),
                "title": title,
                "offset": start,
                "snippet": content[start:end][:600],
            }
        )
    return hits


# --------------------------------------------------------------------- 写入

async def create_material(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    upload: UploadFile,
    title: str | None,
    subject: str | None,
    tags: list[str],
) -> Material:
    original_name = files.sanitize_filename(upload.filename)
    default_title = Path(original_name).stem[:200] or "未命名资料"

    # 上传上限可配（功能 13.5）：配置表优先，兜底 .env
    max_mb = await setting_service.get_int(db, "upload.max_mb")
    saved = await files.save_upload(
        upload, owner_id=user_id, max_bytes=max_mb * 1024 * 1024
    )

    material = Material(
        user_id=user_id,
        title=(title or default_title)[:200],
        subject=subject,
        tags=tags,
        file_name=original_name,
        file_ext=saved.file_ext,
        mime_type=saved.mime_type,
        size_bytes=saved.size_bytes,
        file_path=saved.relative_path,
        file_hash=saved.file_hash,
        parse_status="pending",
    )

    try:
        db.add(material)
        await db.commit()
        await db.refresh(material)
    except Exception:
        # 入库失败就把刚落的文件删掉，避免孤儿文件
        await db.rollback()
        files.delete_file(saved.relative_path)
        raise

    return material


async def update_material(
    db: AsyncSession, material: Material, data: MaterialUpdate
) -> Material:
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(material, field, value)
    material.updated_at = utcnow()
    await db.commit()
    await db.refresh(material)
    return material


async def delete_material(db: AsyncSession, material: Material) -> None:
    """软删除 + 删磁盘文件（docs/api.md §5）。"""
    material.deleted_at = utcnow()
    material.updated_at = utcnow()
    await db.commit()
    files.delete_file(material.file_path)


async def reparse(db: AsyncSession, material: Material) -> Material:
    if material.parse_status not in ("failed", "unsupported"):
        raise BadRequest("仅在解析失败或为扫描版时才能重新解析")
    material.parse_status = "pending"
    material.parse_error = None
    material.updated_at = utcnow()
    await db.commit()
    await db.refresh(material)
    return material


# --------------------------------------------------------------------- 正文分片


async def read_text_chunk(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    material_id: uuid.UUID,
    offset: int,
    limit: int,
) -> MaterialTextOut:
    """按字符偏移读取正文。

    ⚠️ M5 的 agent 工具 read_material_chunk 会复用本函数 —— 不要另写一份，
    否则截断规则与越权判断会出现两套（docs/agent-tools.md §3.3）。
    """
    material = await get_owned(db, user_id, material_id)
    text = material.extracted_text or ""
    total = len(text)
    chunk = text[offset : offset + limit]
    return MaterialTextOut(
        material_id=material.id,
        offset=offset,
        limit=limit,
        total_chars=total,
        has_more=offset + len(chunk) < total,
        text=chunk,
    )


# --------------------------------------------------------------------- 后台解析


async def parse_material(material_id: uuid.UUID, db: AsyncSession | None = None) -> None:
    """解析任务（BackgroundTasks 调用）。

    默认使用**独立的 session**：请求的 session 在响应返回后已关闭。
    测试可以传入自己的 session（见 tests/api/test_materials.py），
    这样解析仍发生在测试事务里，不会污染数据库。

    状态机：pending → parsing → success / failed / unsupported
    """
    if db is not None:
        await _parse_with_session(material_id, db)
        return
    async with SessionLocal() as session:
        await _parse_with_session(material_id, session)


async def _parse_with_session(material_id: uuid.UUID, db: AsyncSession) -> None:
    material = await db.get(Material, material_id)
    if material is None or material.deleted_at is not None:
        return

    material.parse_status = "parsing"
    material.updated_at = utcnow()
    await db.commit()

    try:
        path = files.resolve_safe(material.file_path)
        # 解析是 CPU 密集操作，必须放线程池，否则会卡住事件循环
        parsed = await run_in_threadpool(doc_parser.parse_document, path, material.file_ext)
    except doc_parser.DocumentParseError as exc:
        material.parse_status = "failed"
        material.parse_error = str(exc)[:500]
    except Exception as exc:  # 任何解析异常都要落库而不是崩掉后台任务
        logger.exception("解析资料异常: %s", material_id)
        material.parse_status = "failed"
        material.parse_error = f"解析异常: {type(exc).__name__}"
    else:
        material.page_count = parsed.page_count
        material.char_count = parsed.char_count
        material.extracted_text = parsed.text or None
        material.parsed_at = utcnow()
        if parsed.is_scanned:
            material.parse_status = "unsupported"
            material.parse_error = "扫描版文件没有文本层，暂不支持 OCR"
        else:
            material.parse_status = "success"
            material.parse_error = None

    material.updated_at = utcnow()
    await db.commit()
    logger.info(
        "资料解析完成: %s -> %s (%s 字符)",
        material_id,
        material.parse_status,
        material.char_count,
    )
