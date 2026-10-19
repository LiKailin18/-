"""SQLModel 表模型统一导出包。

⚠️ alembic/env.py 只 import 本包（见 CLAUDE.md §11）：
   新增任何表模型，都必须在这里显式 import，否则 autogenerate 会漏表。

表结构一律先在 docs/db.md 定义，再写模型。
"""

from app.models.admin import AdminAuditLog, AppSetting
from app.models.ai import AiGeneration, AiUsage
from app.models.chat import ChatMessage, ChatSession
from app.models.material import Material
from app.models.note import Note
from app.models.plan import StudyPlan
from app.models.quiz import Quiz, QuizAttempt
from app.models.record import StudyRecord
from app.models.task import StudyTask
from app.models.user import AppUser, utcnow

__all__ = [
    "AdminAuditLog",
    "AiGeneration",
    "AiUsage",
    "AppSetting",
    "AppUser",
    "ChatMessage",
    "ChatSession",
    "Material",
    "Note",
    "Quiz",
    "QuizAttempt",
    "StudyPlan",
    "StudyRecord",
    "StudyTask",
    "utcnow",
]
