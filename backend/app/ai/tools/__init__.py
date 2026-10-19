"""Agent 工具包（契约：docs/agent-tools.md §1–§3）。

四条铁律（违反任何一条都算设计错误）：
1. **只读**：绝不写库；写操作由 service 层在拿到 agent 结果后执行
2. **user_id 不进参数**：用工厂闭包绑定，避免提示注入伪造身份
3. **返回必须截断**：单次 ≤ MAX_TOOL_CHARS
4. **不抛异常**：失败返回 {"ok": false, "error": ...} 让模型自行调整
"""

from app.ai.tools.constants import MAX_TOOL_CHARS
from app.ai.tools.materials import (
    make_list_materials,
    make_read_material_chunk,
    make_search_material,
)
from app.ai.tools.notes import make_search_notes
from app.ai.tools.stats import make_get_study_stats, make_get_weak_points
from app.ai.tools.tasks import make_list_pending_tasks

__all__ = [
    "MAX_TOOL_CHARS",
    "make_get_study_stats",
    "make_get_weak_points",
    "make_list_materials",
    "make_list_pending_tasks",
    "make_read_material_chunk",
    "make_search_material",
    "make_search_notes",
]
