"""C5 response engine: lifecycle state, status history, response windows, simulated actions and
the append-only audit trail (C5 Week 2, decisions D1 and D7)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_FUNCTION = """
CREATE FUNCTION audit_records_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_records is append-only: % refused', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$
"""
APPEND_ONLY_TRIGGER = """
CREATE TRIGGER audit_records_append_only
BEFORE UPDATE OR DELETE ON audit_records
FOR EACH ROW EXECUTE FUNCTION audit_records_append_only()
"""


def upgrade() -> None:
    op.create_table(
        "audit_records",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("record_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("incident_id", sa.String(length=128), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("record_id"),
    )
    op.create_index("audit_by_incident", "audit_records", ["incident_id", "seq"], unique=False)
    op.create_table(
        "incident_lifecycle",
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("isolated", sa.Boolean(), nullable=False),
        sa.Column("target_host", sa.Text(), nullable=True),
        sa.Column("target_source_ip", sa.String(length=64), nullable=True),
        sa.Column("target_account", sa.Text(), nullable=True),
        sa.Column("incident_type", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("recommended_scenario_id", sa.String(length=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('new', 'under_analysis', 'awaiting_human_decision', "
            "'response_in_progress', 'escalated', 'resolved', 'closed')",
            name="incident_lifecycle_status",
        ),
        sa.PrimaryKeyConstraint("incident_id"),
    )
    op.create_table(
        "incident_status_history",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("transition_id", sa.String(length=8), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incident_lifecycle.incident_id"],
        ),
        sa.PrimaryKeyConstraint("seq"),
    )
    op.create_index(
        op.f("ix_incident_status_history_incident_id"),
        "incident_status_history",
        ["incident_id"],
        unique=False,
    )
    op.create_table(
        "response_windows",
        sa.Column("window_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recommended_scenario_id", sa.String(length=2), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'decided', 'expired')", name="response_windows_status"
        ),
        sa.CheckConstraint("deadline_at > started_at", name="response_windows_deadline"),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incident_lifecycle.incident_id"],
        ),
        sa.PrimaryKeyConstraint("window_id"),
    )
    op.create_index(
        "response_windows_due", "response_windows", ["status", "deadline_at"], unique=False
    )
    op.create_index(
        "response_windows_one_open",
        "response_windows",
        ["incident_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "response_actions",
        sa.Column("action_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("window_id", sa.String(length=128), nullable=True),
        sa.Column("scenario_id", sa.String(length=2), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("simulated", name="response_actions_simulated"),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incident_lifecycle.incident_id"],
        ),
        sa.ForeignKeyConstraint(
            ["window_id"],
            ["response_windows.window_id"],
        ),
        sa.PrimaryKeyConstraint("action_id"),
    )
    op.create_index(
        op.f("ix_response_actions_incident_id"), "response_actions", ["incident_id"], unique=False
    )
    # C-14, decision D7: the application may add audit records but never change or delete them.
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_records_append_only ON audit_records")
    op.execute("DROP FUNCTION IF EXISTS audit_records_append_only()")
    op.drop_index(op.f("ix_response_actions_incident_id"), table_name="response_actions")
    op.drop_table("response_actions")
    op.drop_index(
        "response_windows_one_open",
        table_name="response_windows",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index("response_windows_due", table_name="response_windows")
    op.drop_table("response_windows")
    op.drop_index(
        op.f("ix_incident_status_history_incident_id"), table_name="incident_status_history"
    )
    op.drop_table("incident_status_history")
    op.drop_table("incident_lifecycle")
    op.drop_index("audit_by_incident", table_name="audit_records")
    op.drop_table("audit_records")
