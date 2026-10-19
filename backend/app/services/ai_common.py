"""AI 场景共用的编排：配额 → 调用 → 二次校验（硬伤重试一次）→ 用量落库。

放在这里而不是每个 service 各写一遍（CLAUDE.md §14：先复用，再新增）。
"""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime import AgentUsage, invoke_structured
from app.core.exceptions import AiOutputInvalid


def merge_usage(first: AgentUsage, second: AgentUsage) -> AgentUsage:
    """两次调用的用量合计（重试消耗的 token 也要算进去）。"""
    return AgentUsage(
        prompt_tokens=first.prompt_tokens + second.prompt_tokens,
        completion_tokens=first.completion_tokens + second.completion_tokens,
        steps=first.steps + second.steps,
        latency_ms=first.latency_ms + second.latency_ms,
    )


async def structured_with_retry(
    scene: str,
    *,
    user_id: uuid.UUID,
    db: AsyncSession,
    message: str,
    validator: Callable[[Any], Any],
    invalid_errors: tuple[type[BaseException], ...],
) -> tuple[Any, AgentUsage, int]:
    """跑一次结构化场景并做业务校验；只有**硬伤**才重试一次。

    返回 (校验后的结果, 累计用量, 重试次数)。
    """
    result, usage = await invoke_structured(scene, user_id=user_id, db=db, user_message=message)

    try:
        return validator(result), usage, 0
    except invalid_errors as exc:
        # 把不合格的原因回灌给模型，明确要求按结构重出
        retry_message = f"{message}\n\n【上次输出不合格】{exc}\n请严格按给定结构重新输出。"
        retried, retry_usage = await invoke_structured(
            scene, user_id=user_id, db=db, user_message=retry_message
        )
        try:
            return validator(retried), merge_usage(usage, retry_usage), 1
        except invalid_errors as exc2:
            raise AiOutputInvalid(f"AI 输出两次都不合格：{exc2}") from exc2
