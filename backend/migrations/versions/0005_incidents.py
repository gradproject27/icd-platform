"""Stored incidents and their event links (C1 Week 3, incident storage)

Numbered in merge order (team plan W3-D2): 0004 is C2's masking maps.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("upload_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("incident_type", sa.Text(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column("first_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_config_version", sa.String(length=64), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.upload_id"]),
        sa.PrimaryKeyConstraint("incident_id"),
    )
    op.create_index(
        "incidents_by_upload", "incidents", ["upload_id", "first_event_at"], unique=False
    )
    op.create_table(
        "incident_events",
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("upload_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("link_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('flagged', 'context')", name="incident_events_role"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.incident_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id", "event_id"], ["events.upload_id", "events.event_id"]),
        sa.PrimaryKeyConstraint("incident_id", "event_id"),
    )
    op.create_index(
        "incident_events_by_event", "incident_events", ["upload_id", "event_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("incident_events_by_event", table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index("incidents_by_upload", table_name="incidents")
    op.drop_table("incidents")
