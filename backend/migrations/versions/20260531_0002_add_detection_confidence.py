"""Add detection confidence columns.

Revision ID: 20260531_0002
Revises: 20260531_0001
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260531_0002"
down_revision: str | None = "20260531_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "detections", sa.Column("detector_confidence", sa.Float(), nullable=True)
    )
    op.add_column("detections", sa.Column("ocr_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "ocr_confidence")
    op.drop_column("detections", "detector_confidence")
