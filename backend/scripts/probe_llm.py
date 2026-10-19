# =====================================================================
# probe_llm.py - LLM capability probe (M5 day one, docs/agent-tools.md #11)
#
# Verifies the THREE capabilities the whole AI layer depends on:
#   1. tool calling      - the model calls a tool and consumes its result
#   2. structured output - response_format=<Pydantic> returns a validated object
#   3. streaming         - astream yields incremental chunks
#
# Usage (from backend/, with the venv active or via full path):
#   .venv\Scripts\python scripts\probe_llm.py
#
# Reads LLM_BASE_URL / LLM_MODEL / LLM_API_KEY from backend/.env.
# Paste the output into docs/dev-notes.md section 2.
#
# Keep this file ASCII-only: PowerShell 5.1 reads scripts with the system
# ANSI code page and mangles non-ASCII text.
# =====================================================================

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Literal

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain.agents import create_agent  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.core.config import settings  # noqa: E402


class ProbeQuiz(BaseModel):
    """Small structured-output schema (mirrors the real QuizOut shape)."""

    title: str = Field(min_length=2, max_length=100)
    type: Literal["single", "judge"]
    options: list[str] = Field(min_length=2, max_length=4)
    answer: str


@tool
def get_fixed_study_minutes(days: int = 7) -> dict:
    """Return fixed study statistics used only by this probe."""
    return {"ok": True, "data": {"days": days, "total_minutes": 123}, "meta": {"count": 1}}


def build_model():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=0,
        timeout=settings.llm_timeout,
        max_retries=0,
    )


def _all_calls(messages) -> list[dict]:
    calls = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            calls.append(call)
    return calls


def probe_tool_calling(model) -> tuple[bool, str]:
    graph = create_agent(
        model=model,
        tools=[get_fixed_study_minutes],
        system_prompt="You are a helpful assistant. Always use the available tool.",
    )
    question = "How many minutes did I study in the last 7 days? Use the tool."
    result = graph.invoke({"messages": [{"role": "user", "content": question}]})
    messages = result.get("messages", [])

    called = any(call.get("name") == "get_fixed_study_minutes" for call in _all_calls(messages))
    text = "".join(m.content for m in messages if isinstance(m.content, str))
    return (called and "123" in text), f"tool_called={called} answer_has_123={'123' in text}"


def probe_structured_output(model) -> tuple[bool, str]:
    prompt = (
        "Produce one single-choice question about the definition of a limit. "
        "Give exactly 4 options and set answer to the option text itself."
    )
    graph = create_agent(
        model=model,
        tools=None,
        system_prompt=prompt,
        response_format=ProbeQuiz,
    )
    result = graph.invoke({"messages": [{"role": "user", "content": "Generate one question."}]})
    structured = result.get("structured_response")
    if structured is None:
        return False, "structured_response is missing"

    options = [option.strip() for option in structured.options]
    in_options = structured.answer.strip() in options
    detail = (
        f"title={structured.title!r} type={structured.type} "
        f"options={len(options)} answer_in_options={in_options}"
    )
    return in_options, detail


def probe_streaming(model) -> tuple[bool, str]:
    """用与生产一致的路径探流式：create_agent 的 graph.astream(stream_mode="messages")。

    注意：裸 ChatOpenAI 的 .stream() 只产出 chunk；(chunk, metadata) 二元组是
    LangGraph 的 stream_mode="messages" 才有的形状（app/ai/runtime.py 用的就是它）。
    """
    graph = create_agent(model=model, tools=None, system_prompt="You are concise.")
    chunks = 0
    text: list[str] = []
    for chunk, _metadata in graph.stream(
        {"messages": [{"role": "user", "content": "Count from 1 to 5, one number per line."}]},
        stream_mode="messages",
    ):
        content = getattr(chunk, "content", "")
        if isinstance(content, str) and content:
            chunks += 1
            text.append(content)
    return chunks >= 2, f"chunks={chunks} text={''.join(text)[:60]!r}"


def main() -> int:
    has_key = bool(settings.llm_api_key.strip())
    key_state = "set" if has_key else "MISSING"
    print("=" * 72)
    print("LLM capability probe")
    print(f"  base_url : {settings.llm_base_url}")
    print(f"  model    : {settings.llm_model}")
    print(f"  api_key  : {key_state}")
    print("=" * 72)

    if not has_key:
        print("\n[SKIP] LLM_API_KEY is empty. Fill it in backend/.env and run again.")
        return 2

    model = build_model()
    checks = [
        ("1. tool calling", probe_tool_calling),
        ("2. structured output", probe_structured_output),
        ("3. streaming", probe_streaming),
    ]

    failures = 0
    for name, probe in checks:
        started = time.perf_counter()
        try:
            ok, detail = probe(model)
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"[:200]
        elapsed = time.perf_counter() - started
        if not ok:
            failures += 1
        print(f"\n[{'PASS' if ok else 'FAIL'}] {name}  ({elapsed:.1f}s)\n        {detail}")

    print("\n" + "=" * 72)
    if failures:
        print(f"RESULT: {failures} check(s) failed. Fallbacks (docs/agent-tools.md #11):")
        print("  - tool calling fails      -> switch to a model with function calling")
        print("  - structured output fails -> confirm tool strategy; else parse JSON text")
        print("  - streaming fails         -> non-stream endpoint + skeleton UI")
    else:
        print("RESULT: all 3 checks passed. Paste this output into docs/dev-notes.md #2.")
    print("=" * 72)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
