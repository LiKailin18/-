"""文本处理工具：标签清洗、摘要、LIKE 转义。

资料与笔记模块共用（CLAUDE.md §14：先复用，再新增）。
"""

import re

TAG_MAX_LENGTH = 32
TAG_MAX_COUNT = 20

_WHITESPACE = re.compile(r"\s+")


def normalize_tags(tags: list[str] | None) -> list[str] | None:
    """去空白、去重（保序）、限制单个长度与总数。"""
    if tags is None:
        return None
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in tags:
        tag = (raw or "").strip()
        if tag and tag not in seen and len(tag) <= TAG_MAX_LENGTH:
            seen.add(tag)
            cleaned.append(tag)
        if len(cleaned) >= TAG_MAX_COUNT:
            break
    return cleaned


def parse_tag_string(raw: str | None) -> list[str]:
    """把表单里的「逗号分隔」标签转成列表（契约 docs/api.md §5）。"""
    if not raw:
        return []
    return normalize_tags(raw.split(",")) or []


def make_excerpt(content: str | None, limit: int = 120) -> str:
    """列表页用的摘要：压平空白后截断，避免列表返回正文。"""
    if not content:
        return ""
    flat = _WHITESPACE.sub(" ", content).strip()
    return flat if len(flat) <= limit else f"{flat[:limit]}…"


def escape_like(keyword: str) -> str:
    """转义 LIKE 通配符，防止用户输入 % / _ 影响匹配。"""
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
