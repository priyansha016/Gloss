"""004 job progress stage

Revision ID: 004
Revises: 003
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Human-readable pipeline stage ("Building glossary…"), shown while processing.
    op.add_column("jobs", sa.Column("progress", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "progress")
