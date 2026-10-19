"""模型入口：整个项目只在这里构造 ChatOpenAI。

换供应商只改环境变量（LLM_BASE_URL / LLM_MODEL / LLM_API_KEY），业务代码不动。
未配置 Key 时抛 AiNotConfigured（503），接口层据此给出「功能未开启」而不是 500。
"""

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.exceptions import AiNotConfigured


def has_api_key() -> bool:
    return bool((settings.llm_api_key or "").strip())


def build_chat_model(*, temperature: float = 0.2) -> ChatOpenAI:
    """构造模型实例。

    ⚠️ `timeout` 只作用于**单次模型请求**，管不住多轮工具调用的总时长 ——
    整轮超时要靠 runtime.py 里的 asyncio.wait_for（docs/agent-tools.md §9）。
    """
    if not has_api_key():
        raise AiNotConfigured

    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=temperature,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )
