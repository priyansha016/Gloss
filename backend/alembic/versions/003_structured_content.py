"""003 structured section/doc content

Revision ID: 003
Revises: 002
Create Date: 2026-07-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rich, structured study-note content (bullets, worked-example steps, diagrams).
    # summary_short/summary_full/tldr are kept as plain-text fallbacks.
    op.add_column("sections", sa.Column("content", postgresql.JSONB, nullable=True))
    op.add_column("doc_summaries", sa.Column("content", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("doc_summaries", "content")
    op.drop_column("sections", "content")
