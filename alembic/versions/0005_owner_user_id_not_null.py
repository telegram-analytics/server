"""Placeholder. Post-rollout migration that enforces NOT NULL on projects.owner_user_id and later drops admin_chat_id. Intentionally empty until all handlers are migrated off admin_chat_id (Phase 3). Filled in during Phase 3's contract step.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24 00:00:00.000000

"""

from collections.abc import Sequence

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
