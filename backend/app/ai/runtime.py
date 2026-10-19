"""调用编排：超时、步数上限、用量累加、异常映射。

三个必须记住的点（CLAUDE.md §11）：
1. `ChatOpenAI(timeout=)` 只管**单次**模型请求，整轮 agent 循环用 asyncio.wait_for 兜底
2. token 要遍历**所有** AIMessage 累加（agent 是多轮调用，只取最后一条会严重低估）
3. 上游异常一律映射成契约里的错误码，不把原始堆栈抛给前端
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import Scene, build_agent
from app.core.config import settings
from app.core.exceptions import (
    AiOutputInvalid,
    AiStepsExceeded,
    AiTimeout,
    AiUpstreamError,
)

try:  # 版本差异兜底：拿不到这个异常类型也不能让整条链路崩掉
    from langgraph.errors import GraphRecursionError
except ImportError:  # pragma: no cover
    class GraphRecursionError(Exception):  # type: ignore[no-redef]
        pass


@dataclass
class AgentUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    steps: int = 0
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def accumulate_usage(messages: list[Any], *, latency_ms: int = 0) -> AgentUsage:
    """从图返回的 messages 里累加用量。"""
    prompt = completion = steps = 0
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        steps += 1
        usage = getattr(message, "usage_metadata", None) or {}
        prompt += int(usage.get("input_tokens", 0) or 0)
        completion += int(usage.get("output_tokens", 0) or 0)
    return AgentUsage(
        prompt_tokens=prompt, completion_tokens=completion, steps=steps, latency_ms=latency_ms
    )


def collect_tool_calls(messages: list[Any]) -> list[dict]:
    """收集本轮实际调用过的工具（供前端展示与调试）。"""
    calls: list[dict] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in getattr(message, "tool_calls", None) or []:
            calls.append({"name": call.get("name"), "args": call.get("args")})
    return calls


def _config() -> dict:
    return {"recursion_limit": settings.llm_max_steps}


async def invoke_structured(
    scene: Scene, *, user_id: uuid.UUID, db: AsyncSession, user_message: str
):
    """跑一次结构化输出场景，返回 (结构化结果, 用量)。"""
    graph = build_agent(scene, user_id=user_id, db=db)
    started = time.perf_counter()

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                {"messages": [{"role": "user", "content": user_message}]}, config=_config()
            ),
            timeout=settings.ai_agent_timeout,
        )
    except TimeoutError as exc:
        raise AiTimeout from exc
    except GraphRecursionError as exc:
        raise AiStepsExceeded from exc
    except Exception as exc:
        raise AiUpstreamError from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    structured = result.get("structured_response") if isinstance(result, dict) else None
    if structured is None:
        raise AiOutputInvalid("模型没有返回结构化结果")

    usage = accumulate_usage(result.get("messages", []), latency_ms=latency_ms)
    return structured, usage


async def invoke_text(
    scene: Scene, *, user_id: uuid.UUID, db: AsyncSession, messages: list[dict]
) -> tuple[str, list[dict], AgentUsage]:
    """跑一次纯文本场景（非流式），返回 (回答文本, 工具调用, 用量)。"""
    graph = build_agent(scene, user_id=user_id, db=db)
    started = time.perf_counter()

    try:
        result = await asyncio.wait_for(
            graph.ainvoke({"messages": messages}, config=_config()),
            timeout=settings.ai_agent_timeout,
        )
    except TimeoutError as exc:
        raise AiTimeout from exc
    except GraphRecursionError as exc:
        raise AiStepsExceeded from exc
    except Exception as exc:
        raise AiUpstreamError from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    returned = result.get("messages", [])
    answer = ""
    for message in reversed(returned):
        if isinstance(message, AIMessage) and isinstance(message.content, str) and message.content:
            answer = message.content
            break

    usage = accumulate_usage(returned, latency_ms=latency_ms)
    return answer, collect_tool_calls(returned), usage


async def stream_text(
    scene: Scene, *, user_id: uuid.UUID, db: AsyncSession, messages: list[dict]
) -> AsyncIterator[dict]:
    """流式跑一次场景，逐个 yield SSE 事件（契约：docs/api.md §13）。

    事件序列：meta(由上层发) → tool* → delta* → done
    任何异常都会映射成 error 事件，**不能让连接静默中断**。
    """
    graph = build_agent(scene, user_id=user_id, db=db)
    started = time.perf_counter()
    prompt_tokens = completion_tokens = steps = 0
    collected_text: list[str] = []
    tool_calls: list[dict] = []
    announced: set[str] = set()

    try:
        async for chunk, _metadata in graph.astream(
            {"messages": messages}, config=_config(), stream_mode="messages"
        ):
            # 工具调用：chunk 里带 tool_call_chunks 时广播一次 start 事件
            for call in getattr(chunk, "tool_call_chunks", None) or []:
                name = call.get("name")
                if name and name not in announced:
                    announced.add(name)
                    tool_calls.append({"name": name, "args": {}})
                    yield {"event": "tool", "data": {"name": name, "status": "start"}}

            usage = getattr(chunk, "usage_metadata", None)
            if usage:
                prompt_tokens += int(usage.get("input_tokens", 0) or 0)
                completion_tokens += int(usage.get("output_tokens", 0) or 0)
                steps += 1

            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                collected_text.append(text)
                yield {"event": "delta", "data": {"text": text}}

    except TimeoutError:
        # 整轮超时：已输出的内容保留，由上层记录 ok=false
        raise AiTimeout from None
    except GraphRecursionError as exc:
        raise AiStepsExceeded from exc
    except Exception as exc:
        raise AiUpstreamError from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage_result = AgentUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        steps=max(steps, 1),
        latency_ms=latency_ms,
    )
    yield {
        "event": "done",
        "data": {
            "text": "".join(collected_text),
            "tool_calls": tool_calls,
            "usage": usage_result,
        },
    }
