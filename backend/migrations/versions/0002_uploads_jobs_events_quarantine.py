"""uploads, jobs, stored events and quarantined records (C1 Week 2, decision D6)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("upload_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("upload_id"),
    )
    op.create_index(op.f("ix_uploads_sha256"), "uploads", ["sha256"], unique=False)
    op.create_table(
        "events",
        sa.Column("upload_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label_status", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=True),
        sa.Column("src_ip", sa.String(length=64), nullable=True),
        sa.Column("dst_ip", sa.String(length=64), nullable=True),
        sa.Column("user", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.upload_id"],
        ),
        sa.PrimaryKeyConstraint("upload_id", "event_id"),
    )
    op.create_index(
        "events_by_label", "events", ["upload_id", "label_status", "event_id"], unique=False
    )
    op.create_index(op.f("ix_events_timestamp"), "events", ["timestamp"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("upload_id", sa.String(length=128), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("kind IN ('ingest', 'analysis')", name="jobs_kind"),
        sa.CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="jobs_state"),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.upload_id"],
        ),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(op.f("ix_jobs_upload_id"), "jobs", ["upload_id"], unique=True)
    op.create_index("jobs_queue", "jobs", ["state", "created_at"], unique=False)
    op.create_table(
        "quarantined_records",
        sa.Column("upload_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("record_ref", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_excerpt", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.upload_id"],
        ),
        sa.PrimaryKeyConstraint("upload_id", "seq"),
    )


def downgrade() -> None:
    op.drop_table("quarantined_records")
    op.drop_index("jobs_queue", table_name="jobs")
    op.drop_index(op.f("ix_jobs_upload_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_events_timestamp"), table_name="events")
    op.drop_index("events_by_label", table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_uploads_sha256"), table_name="uploads")
    op.drop_table("uploads")
