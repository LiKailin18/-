"""AI 资料总结（功能 8）。

长文档走 map-reduce：分段总结后再合并，避免把整本书一次性塞进上下文。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import usage as usage_module
from app.ai.chunking import split_for_summary
from app.ai.validators import SummaryInvalidError, validate_summary
from app.core.config import settings
from app.core.exceptions import AiOutputInvalid, MaterialNotParsed, ScannedUnsupported
from app.models import AiGeneration, AppUser, Material
from app.schemas.ai import SummaryCreate
from app.services import ai_common, material_service

STYLE_HINTS = {
    "outline": "以提纲形式总结，突出层次结构",
    "key_points": "以要点清单形式总结，每条一句话",
    "detailed": "详细展开，保留关键推理过程与公式",
}


def _ensure_parsable(material: Material) -> None:
    if material.parse_status == "unsupported":
        raise ScannedUnsupported
    if material.parse_status != "success":
        raise MaterialNotParsed


def _slice(text: str, start: int, end: int | None) -> str:
    return text[start:end] if end else text[start:]


def _direct_message(material: Material, text: str, style: str, scope_start: int) -> str:
    return (
        f"资料标题：{material.title}\n"
        f"字符范围：{scope_start} - {scope_start + len(text)}（共 {material.char_count} 字）\n"
        f"总结风格：{STYLE_HINTS[style]}\n\n"
        f"需要总结的正文如下（已按范围截取，直接基于它总结）：\n"
        f"-----\n{text}\n-----"
    )


async def generate(
    db: AsyncSession, *, user: AppUser, data: SummaryCreate
) -> tuple[AiGeneration, int]:
    """生成总结并归档；返回 (归档记录, 重试次数)。"""
    await usage_module.ensure_quota(db, user_id=user.id)

    material = await material_service.get_owned(db, user.id, data.material_id)
    _ensure_parsable(material)

    text = _slice(material.extracted_text or "", data.scope_start, data.scope_end or None)
    if not text.strip():
        raise MaterialNotParsed("资料正文为空，无法总结")

    scope = {"start": data.scope_start, "end": data.scope_end}
    char_count = len(text)

    if char_count <= settings.llm_max_input_chars:
        result, usage, retries = await ai_common.structured_with_retry(
            "summary",
            user_id=user.id,
            db=db,
            message=_direct_message(material, text, data.style, data.scope_start),
            validator=validate_summary,
            invalid_errors=(SummaryInvalidError,),
        )
        mode, segments = "direct", 1
    else:
        # map：分段各自总结；reduce：把分段结论合并成最终总结
        chunks = split_for_summary(text)
        partials: list[str] = []
        usage = None
        for index, chunk in enumerate(chunks, start=1):
            part, part_usage, _ = await ai_common.structured_with_retry(
                "summary",
                user_id=user.id,
                db=db,
                message=(
                    f"这是《{material.title}》的第 {index}/{len(chunks)} 段，"
                    f"请只总结本段内容（风格：{STYLE_HINTS[data.style]}）。\n"
                    f"-----\n{chunk}\n-----"
                ),
                validator=validate_summary,
                invalid_errors=(SummaryInvalidError,),
            )
            partials.append(part.summary_md)
            usage = part_usage if usage is None else ai_common.merge_usage(usage, part_usage)

        combined = "\n\n".join(partials)[: settings.llm_max_input_chars]
        result, reduce_usage, retries = await ai_common.structured_with_retry(
            "summary",
            user_id=user.id,
            db=db,
            message=(
                f"以下是《{material.title}》各分段的总结，请合并成一份完整的总结"
                f"（风格：{STYLE_HINTS[data.style]}），不要出现「本段」之类的措辞：\n\n{combined}"
            ),
            validator=validate_summary,
            invalid_errors=(SummaryInvalidError,),
        )
        usage = ai_common.merge_usage(usage, reduce_usage)
        mode, segments = "map_reduce", len(chunks)

    row = AiGeneration(
        user_id=user.id,
        scene="summary",
        ref_type="material",
        ref_id=material.id,
        input_params={"style": data.style, "scope": scope},
        output_md=result.summary_md,
        output_data={
            "key_points": result.key_points,
            "style": data.style,
            "mode": mode,
            "segments": segments,
            "char_count": char_count,
            "scope": scope,
        },
        model=settings.llm_model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_ms=usage.latency_ms,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await usage_module.record_usage(
        db, user_id=user.id, scene="summary", model=settings.llm_model, usage=usage
    )
    return row, retries


async def list_summaries(
    db: AsyncSession, *, user_id: uuid.UUID, offset: int, limit: int, material_id: uuid.UUID | None
) -> tuple[list[AiGeneration], int]:
    from sqlalchemy import func

    conditions = [
        AiGeneration.user_id == user_id,
        AiGeneration.scene == "summary",
    ]
    if material_id:
        conditions.append(AiGeneration.ref_id == material_id)

    total = await db.scalar(select(func.count()).select_from(AiGeneration).where(*conditions))
    rows = (
        await db.execute(
            select(AiGeneration)
            .where(*conditions)
            .order_by(AiGeneration.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total or 0)


async def get_owned(db: AsyncSession, user_id: uuid.UUID, summary_id: uuid.UUID) -> AiGeneration:
    from app.core.exceptions import NotFound

    row = await db.scalar(
        select(AiGeneration).where(
            AiGeneration.id == summary_id,
            AiGeneration.user_id == user_id,
            AiGeneration.scene == "summary",
        )
    )
    if row is None:
        raise NotFound("总结不存在")
    return row


__all__ = ["AiOutputInvalid", "generate", "get_owned", "list_summaries"]
