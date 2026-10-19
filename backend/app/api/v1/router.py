"""v1 业务路由汇总。

按功能编号挂载，一个功能一个模块（CLAUDE.md §5.1）：

    1  认证   → api/v1/auth.py
    2  用户   → api/v1/users.py
    3  资料   → api/v1/materials.py
    4  笔记   → api/v1/notes.py
    5  计划   → api/v1/plans.py
    6  任务   → api/v1/tasks.py
    7  问答   → api/v1/ai.py（chat-sessions）
    8  总结   → api/v1/ai.py（summaries）
    9  测试题 → api/v1/quizzes.py
    10 推荐   → api/v1/stats.py（recommendations，规则层）＋ api/v1/ai.py（advice，AI 层）
    11 统计   → api/v1/stats.py
    12 记录   → api/v1/records.py
    —  文件   → api/v1/files.py（头像等受保护的文件访问）
    ...
    13 管理端 → api/v1/admin/*.py        (M6b)
"""

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    auth,
    files,
    materials,
    notes,
    plans,
    quizzes,
    records,
    stats,
    tasks,
    users,
)

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(materials.router)
api_v1_router.include_router(notes.router)
api_v1_router.include_router(plans.router)
api_v1_router.include_router(tasks.router)
api_v1_router.include_router(records.router)
api_v1_router.include_router(ai.router)
api_v1_router.include_router(quizzes.router)
api_v1_router.include_router(stats.router)
api_v1_router.include_router(files.router)
