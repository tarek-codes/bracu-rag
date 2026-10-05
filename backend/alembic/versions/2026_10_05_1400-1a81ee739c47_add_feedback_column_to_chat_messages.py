"""add feedback column to chat_messages

Revision ID: 1a81ee739c47
Revises: e123456789ab
Create Date: 2026-10-05 14:00:10.848823

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a81ee739c47"
down_revision: str | None = "e123456789ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "feedback")
