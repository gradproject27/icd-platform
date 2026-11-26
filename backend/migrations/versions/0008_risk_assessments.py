"""Append-only risk score records and the confidence job (risk-v1 step 6b, RV1-D17)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_FUNCTION = """
CREATE FUNCTION risk_assessments_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'risk_assessments is append-only: % refused', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER risk_assessments_append_only
BEFORE UPDATE OR DELETE ON risk_assessments
FOR EACH ROW EXECUTE FUNCTION risk_assessments_append_only()
"""


def upgrade() -> None:
    op.create_table(
        "risk_assessments",
        sa.Column("assessment_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("upload_id", sa.String(length=128), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("config_version", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("phase IN ('initial', 'final')", name="risk_assessments_phase"),
        sa.PrimaryKeyConstraint("assessment_id"),
    )
    op.create_index(
        "risk_assessments_by_incident", "risk_assessments", ["incident_id", "assessment_id"]
    )
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)
    # The confidence job (risk-v1 phase 2 on HPC).
    op.drop_constraint("jobs_kind", "jobs", type_="check")
    op.create_check_constraint("jobs_kind", "jobs", "kind IN ('ingest', 'analysis', 'confidence')")


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind = 'confidence'")
    op.drop_constraint("jobs_kind", "jobs", type_="check")
    op.create_check_constraint("jobs_kind", "jobs", "kind IN ('ingest', 'analysis')")
    op.execute("DROP TRIGGER IF EXISTS risk_assessments_append_only ON risk_assessments")
    op.execute("DROP FUNCTION IF EXISTS risk_assessments_append_only()")
    op.drop_index("risk_assessments_by_incident", table_name="risk_assessments")
    op.drop_table("risk_assessments")
