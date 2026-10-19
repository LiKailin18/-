"""文本切分（只用于**送模型**，与检索检索用的 2000 字分片不同）。

两种 chunk 的用途不同，不要混：
- 检索/预览：2000 字左右，片段小、定位准（docs/db.md §1 的正文分片策略）
- 送模型做 map-reduce：接近 `LLM_MAX_INPUT_CHARS`，减少调用次数与总 token
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings


def split_for_summary(text: str, *, chunk_size: int | None = None) -> list[str]:
    size = chunk_size or max(2000, settings.llm_max_input_chars)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=200,
        separators=["\n\n", "\n", "。", "；", " ", ""],
    )
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]
