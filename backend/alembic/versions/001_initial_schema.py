"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    video_status = postgresql.ENUM(
        "queued", "processing", "ready", "failed", "no_captions",
        name="video_status",
        create_type=False,
    )
    job_state = postgresql.ENUM(
        "queued", "processing", "completed", "failed",
        name="job_state",
        create_type=False,
    )
    video_status.create(op.get_bind(), checkfirst=True)
    job_state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("youtube_id", sa.String(20), nullable=False),
        sa.Column("title", sa.String(512)),
        sa.Column("channel", sa.String(256)),
        sa.Column("duration_s", sa.Integer()),
        sa.Column("lang", sa.String(16)),
        sa.Column("status", video_status, nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_videos_youtube_id", "videos", ["youtube_id"], unique=True)

    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), unique=True),
        sa.Column("raw_segments", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("cleaned_segments", postgresql.JSONB),
    )

    op.create_table(
        "sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("summary_short", sa.Text()),
        sa.Column("summary_full", sa.Text()),
    )
    op.create_index("ix_sections_video_id", "sections", ["video_id"])

    op.create_table(
        "doc_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), unique=True),
        sa.Column("tldr", sa.Text()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column("state", job_state, nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_video_id", "jobs", ["video_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_video_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("doc_summaries")
    op.drop_index("ix_sections_video_id", table_name="sections")
    op.drop_table("sections")
    op.drop_table("transcripts")
    op.drop_index("ix_videos_youtube_id", table_name="videos")
    op.drop_table("videos")
    op.execute("DROP TYPE IF EXISTS job_state")
    op.execute("DROP TYPE IF EXISTS video_status")
