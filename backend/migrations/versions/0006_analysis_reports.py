"""Stored AI reports, also the report cache (AI1 Week 3, workflow steps 5 and 11)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_reports",
        sa.Column("report_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_package_id", sa.String(length=128), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("generated_by", sa.String(length=16), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("tries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "generated_by IN ('mock', 'hpc', 'local')", name="analysis_reports_generated_by"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="analysis_reports_confidence"
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.incident_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_index(
        "analysis_reports_by_key", "analysis_reports", ["cache_key", "created_at"], unique=False
    )
    op.create_index(
        "analysis_reports_by_incident",
        "analysis_reports",
        ["incident_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("analysis_reports_by_incident", table_name="analysis_reports")
    op.drop_index("analysis_reports_by_key", table_name="analysis_reports")
    op.drop_table("analysis_reports")
