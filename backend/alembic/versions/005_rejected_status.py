"""005 rejected video status (gatekeeper)

Revision ID: 005
Revises: 004
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE video_status ADD VALUE IF NOT EXISTS 'rejected'")


def downgrade() -> None:
    # Postgres cannot drop enum values; harmless to leave in place.
    pass
