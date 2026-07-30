"""002 glossary tables

Revision ID: 002
Revises: 001
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "glossary_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("term", sa.String(128), nullable=False),
        sa.Column("display", sa.String(128), nullable=False),
        sa.Column("definition_beginner", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768)),
        sa.Column("domain", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_glossary_terms_term", "glossary_terms", ["term"], unique=True)

    op.create_table(
        "term_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column("term_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("glossary_terms.id", ondelete="CASCADE")),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sections.id", ondelete="SET NULL")),
        sa.Column("segment_idx", sa.Integer()),
    )
    op.create_index("ix_term_occurrences_video_id", "term_occurrences", ["video_id"])
    op.create_index("ix_term_occurrences_term_id", "term_occurrences", ["term_id"])


def downgrade() -> None:
    op.drop_index("ix_term_occurrences_term_id", table_name="term_occurrences")
    op.drop_index("ix_term_occurrences_video_id", table_name="term_occurrences")
    op.drop_table("term_occurrences")
    op.drop_index("ix_glossary_terms_term", table_name="glossary_terms")
    op.drop_table("glossary_terms")
