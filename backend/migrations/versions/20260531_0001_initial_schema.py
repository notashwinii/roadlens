"""Create initial Speedotector tables.

Revision ID: 20260531_0001
Revises:
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260531_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("date_processed", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_videos_id"), "videos", ["id"], unique=False)

    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("plate_text", sa.String(length=50), nullable=False),
        sa.Column("x1", sa.Float(), nullable=False),
        sa.Column("y1", sa.Float(), nullable=False),
        sa.Column("x2", sa.Float(), nullable=False),
        sa.Column("y2", sa.Float(), nullable=False),
        sa.Column("crop_width", sa.Integer(), nullable=False),
        sa.Column("crop_height", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_detections_id"), "detections", ["id"], unique=False)
    op.create_index(
        op.f("ix_detections_video_id"), "detections", ["video_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_detections_video_id"), table_name="detections")
    op.drop_index(op.f("ix_detections_id"), table_name="detections")
    op.drop_table("detections")
    op.drop_index(op.f("ix_videos_id"), table_name="videos")
    op.drop_table("videos")
