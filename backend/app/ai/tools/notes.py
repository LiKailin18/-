"""笔记检索工具（可选启用，契约：docs/agent-tools.md §3.7）。

默认关闭（AI_ENABLE_NOTE_TOOL=false）：与资料检索结果高度重叠，启用后模型更容易选错工具。
"""

import uuid

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.constants import MAX_TOOL_CHARS
from app.models import Note
from app.utils.text import escape_like


def make_search_notes(user_id: uuid.UUID, db: AsyncSession):
    """按关键词在本人笔记里检索片段。"""

    @tool
    async def search_notes(keyword: str, limit: int = 3) -> dict:
        """Search the user's own notes and return short matching snippets."""
        if not keyword or not keyword.strip():
            return {"ok": False, "error": "BAD_KEYWORD", "message": "关键词不能为空"}

        safe_limit = max(1, min(limit, 5))
        pattern = f"%{escape_like(keyword.strip())}%"
        rows = (
            await db.execute(
                select(Note)
                .where(
                    Note.user_id == user_id,
                    Note.deleted_at.is_(None),
                    Note.content.ilike(pattern, escape="\\"),
                )
                .order_by(Note.updated_at.desc())
                .limit(safe_limit)
            )
        ).scalars().all()

        hits: list[dict] = []
        total = 0
        truncated = False
        for note in rows:
            position = note.content.lower().find(keyword.strip().lower())
            start = max(0, position - 200)
            snippet = note.content[start : start + 400]
            if total + len(snippet) > MAX_TOOL_CHARS:
                truncated = True
                break
            total += len(snippet)
            hits.append({"note_id": str(note.id), "title": note.title, "snippet": snippet})

        return {
            "ok": True,
            "data": {"hits": hits},
            "meta": {"count": len(hits), "truncated": truncated},
        }

    return search_notes
