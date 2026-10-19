"""资料相关工具（契约：docs/agent-tools.md §3.1–§3.3）。"""

import uuid

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.constants import MAX_TOOL_CHARS
from app.models import Material
from app.services import material_service


def make_list_materials(user_id: uuid.UUID, db: AsyncSession):
    """列出本人资料，供模型获取 material_id。"""

    @tool
    async def list_materials(subject: str | None = None, limit: int = 10) -> dict:
        """List the user's own parsed study materials (id, title, subject, size).

        Only materials whose parsing finished successfully are returned.
        """
        safe_limit = max(1, min(limit, 20))
        conditions = [
            Material.user_id == user_id,
            Material.deleted_at.is_(None),
            Material.parse_status == "success",
        ]
        if subject:
            conditions.append(Material.subject == subject)

        rows = (
            await db.execute(
                select(Material)
                .where(*conditions)
                .order_by(Material.created_at.desc())
                .limit(safe_limit)
            )
        ).scalars().all()

        materials = [
            {
                "id": str(item.id),
                "title": item.title,
                "subject": item.subject,
                "char_count": item.char_count,
                "page_count": item.page_count,
                "tags": item.tags,
            }
            for item in rows
        ]
        return {"ok": True, "data": {"materials": materials}, "meta": {"count": len(materials)}}

    return list_materials


def make_search_material(user_id: uuid.UUID, db: AsyncSession):
    """按关键词在资料正文里检索片段。"""

    @tool
    async def search_material(keyword: str, limit: int = 3) -> dict:
        """Search inside the user's own materials and return matching snippets.

        Returns for each hit: material_id, title, offset and a short snippet.
        An empty result means nothing matched - do not invent content.
        """
        if not keyword or not keyword.strip():
            return {"ok": False, "error": "BAD_KEYWORD", "message": "关键词不能为空"}

        safe_limit = max(1, min(limit, 5))
        hits = await material_service.search_materials(
            db, user_id=user_id, keyword=keyword.strip(), limit=safe_limit
        )

        total = 0
        truncated_hits: list[dict] = []
        truncated = False
        for hit in hits:
            candidate = total + len(hit["snippet"])
            if candidate > MAX_TOOL_CHARS:
                truncated = True
                break
            total = candidate
            truncated_hits.append(hit)

        return {
            "ok": True,
            "data": {"hits": truncated_hits},
            "meta": {"count": len(truncated_hits), "truncated": truncated},
        }

    return search_material


def make_read_material_chunk(user_id: uuid.UUID, db: AsyncSession):
    """按字符偏移分片读取资料正文。"""

    @tool
    async def read_material_chunk(material_id: str, offset: int = 0, limit: int = 4000) -> dict:
        """Read a slice of one material's extracted text by character offset.

        Use offset/has_more to page through a long document. limit is capped at 4000.
        """
        try:
            parsed_id = uuid.UUID(str(material_id))
        except (TypeError, ValueError):
            return {"ok": False, "error": "BAD_ID", "message": "material_id 不是合法的 UUID"}

        safe_limit = max(1, min(limit, 4000))
        safe_offset = max(0, offset)

        try:
            chunk = await material_service.read_text_chunk(
                db,
                user_id=user_id,
                material_id=parsed_id,
                offset=safe_offset,
                limit=safe_limit,
            )
        except Exception:
            # 越权与不存在返回同一个错误（不暴露资源是否存在）
            return {
                "ok": False,
                "error": "MATERIAL_NOT_FOUND",
                "message": "资料不存在或不属于当前用户",
            }

        text = chunk.text
        # has_more 为真说明后面还有内容 —— 对模型来说这份片段就是「被截断了」
        truncated = len(text) > MAX_TOOL_CHARS or chunk.has_more
        return {
            "ok": True,
            "data": {
                "material_id": chunk.material_id,
                "offset": chunk.offset,
                "total_chars": chunk.total_chars,
                "has_more": chunk.has_more,
                "text": text[:MAX_TOOL_CHARS],
            },
            "meta": {"count": 1, "truncated": truncated},
        }

    return read_material_chunk
