"""Add detection creation timestamp.

Revision ID: 20260531_0003
Revises: 20260531_0002
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260531_0003"
down_revision: str | None = "20260531_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "detections",
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    if op.get_context().dialect.name != "sqlite":
        op.alter_column("detections", "created_at", server_default=None)


def downgrade() -> None:
    op.drop_column("detections", "created_at")
