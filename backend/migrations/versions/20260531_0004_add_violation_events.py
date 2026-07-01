"""Add violation events and evidence artifacts.

Revision ID: 20260531_0004
Revises: 20260531_0003
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260531_0004"
down_revision: str | None = "20260531_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "violation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("zone_id", sa.String(length=100), nullable=False),
        sa.Column("zone_type", sa.String(length=50), nullable=False),
        sa.Column("zone_name", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("source_frame_number", sa.Integer(), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=True),
        sa.Column("vehicle_class", sa.String(length=50), nullable=False),
        sa.Column("vehicle_confidence", sa.Float(), nullable=True),
        sa.Column("vehicle_x1", sa.Float(), nullable=False),
        sa.Column("vehicle_y1", sa.Float(), nullable=False),
        sa.Column("vehicle_x2", sa.Float(), nullable=False),
        sa.Column("vehicle_y2", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_violation_events_id"),
        "violation_events",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_violation_events_rule_id"),
        "violation_events",
        ["rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_violation_events_video_id"),
        "violation_events",
        ["video_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_violation_events_zone_id"),
        "violation_events",
        ["zone_id"],
        unique=False,
    )

    op.create_table(
        "evidence_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("violation_event_id", sa.Integer(), nullable=False),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["violation_event_id"], ["violation_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_artifacts_id"),
        "evidence_artifacts",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_artifacts_violation_event_id"),
        "evidence_artifacts",
        ["violation_event_id"],
        unique=False,
    )

    with op.batch_alter_table("detections") as batch_op:
        batch_op.add_column(
            sa.Column("violation_event_id", sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            "ix_detections_violation_event_id",
            ["violation_event_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_detections_violation_event_id_violation_events",
            "violation_events",
            ["violation_event_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("detections") as batch_op:
        batch_op.drop_constraint(
            "fk_detections_violation_event_id_violation_events",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_detections_violation_event_id")
        batch_op.drop_column("violation_event_id")

    op.drop_index(
        op.f("ix_evidence_artifacts_violation_event_id"),
        table_name="evidence_artifacts",
    )
    op.drop_index(op.f("ix_evidence_artifacts_id"), table_name="evidence_artifacts")
    op.drop_table("evidence_artifacts")

    op.drop_index(op.f("ix_violation_events_zone_id"), table_name="violation_events")
    op.drop_index(op.f("ix_violation_events_video_id"), table_name="violation_events")
    op.drop_index(op.f("ix_violation_events_rule_id"), table_name="violation_events")
    op.drop_index(op.f("ix_violation_events_id"), table_name="violation_events")
    op.drop_table("violation_events")
