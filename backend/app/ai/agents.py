"""create_agent 工厂：按场景组装 prompt + tools + response_format。

约定（CLAUDE.md §5.3）：
- 工具只读、user_id 由闭包注入、写库一律回到 service 层
- 每个请求构造一次 agent（工具绑定了当前用户与 db session）
- 温度按场景区分：出题最保守（0.1），建议最灵活（0.4）
"""

import uuid
from typing import Literal

from langchain.agents import create_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import build_chat_model
from app.ai.prompts import load_prompt
from app.ai.schemas import AdviceOut, QuizOut, SummaryOut
from app.ai.tools import (
    make_get_study_stats,
    make_get_weak_points,
    make_list_materials,
    make_list_pending_tasks,
    make_read_material_chunk,
    make_search_material,
    make_search_notes,
)
from app.core.config import settings

Scene = Literal["qa", "summary", "quiz", "advice"]

TEMPERATURES: dict[str, float] = {"qa": 0.3, "summary": 0.2, "quiz": 0.1, "advice": 0.4}


def build_agent(scene: Scene, *, user_id: uuid.UUID, db: AsyncSession):
    """构造某场景的 agent graph。"""
    model = build_chat_model(temperature=TEMPERATURES.get(scene, 0.2))
    system_prompt = load_prompt(scene)

    if scene == "qa":
        tools = [
            make_list_materials(user_id, db),
            make_search_material(user_id, db),
            make_read_material_chunk(user_id, db),
            make_get_study_stats(user_id, db),
        ]
        if settings.ai_enable_note_tool:
            tools.append(make_search_notes(user_id, db))
        return create_agent(model=model, tools=tools, system_prompt=system_prompt)

    # summary / quiz：正文已由 service 层放进 message（见 summary_service._direct_message），
    # **不要**再挂 read_material_chunk —— 模型会反复调用同一工具，直到撞上
    # ai_max_steps（400 AI_005），既慢又贵。
    if scene == "summary":
        return create_agent(
            model=model,
            system_prompt=system_prompt,
            response_format=SummaryOut,
        )

    if scene == "quiz":
        return create_agent(
            model=model,
            system_prompt=system_prompt,
            response_format=QuizOut,
        )

    if scene == "advice":
        return create_agent(
            model=model,
            tools=[
                make_get_study_stats(user_id, db),
                make_get_weak_points(user_id, db),
                make_list_pending_tasks(user_id, db),
            ],
            system_prompt=system_prompt,
            response_format=AdviceOut,
        )

    raise ValueError(f"未知场景: {scene}")
