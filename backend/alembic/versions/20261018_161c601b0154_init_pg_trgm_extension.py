"""init: 创建 pg_trgm 扩展

功能 3/4 的中文模糊搜索依赖 pg_trgm（docs/db.md §1）。
pg_trgm 自 PostgreSQL 13 起是 trusted extension，库属主即可创建，无需超级用户。

Revision ID: 161c601b0154
Revises:
Create Date: 2026-10-18 18:08:06.956098

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "161c601b0154"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建模糊搜索扩展（幂等）。"""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    """移除扩展。

    若后续迁移创建了 trgm 索引，PostgreSQL 会因为存在依赖对象而直接报错拒绝，
    不会静默破坏索引 —— 这正是我们想要的行为。
    """
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
