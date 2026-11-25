"""Simulated IP blocks that end on their own (P2 timed containment, decision D5)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulated_containments",
        sa.Column("containment_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("action_id", sa.String(length=128), nullable=False),
        sa.Column("last_incident_id", sa.String(length=128), nullable=False),
        sa.Column("last_action_id", sa.String(length=128), nullable=False),
        sa.Column("offence", sa.Integer(), nullable=False),
        sa.Column("extended", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_version", sa.String(length=64), nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("kind IN ('block_ip')", name="simulated_containments_kind"),
        sa.CheckConstraint(
            "status IN ('active', 'reverted')", name="simulated_containments_status"
        ),
        sa.CheckConstraint("ends_at > started_at", name="simulated_containments_ends"),
        sa.CheckConstraint("offence >= 1", name="simulated_containments_offence"),
        sa.CheckConstraint("simulated", name="simulated_containments_simulated"),
        sa.CheckConstraint(
            "(status = 'reverted') = (reverted_at IS NOT NULL)",
            name="simulated_containments_reverted_at",
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incident_lifecycle.incident_id"]),
        sa.ForeignKeyConstraint(["last_incident_id"], ["incident_lifecycle.incident_id"]),
        sa.ForeignKeyConstraint(["action_id"], ["response_actions.action_id"]),
        sa.ForeignKeyConstraint(["last_action_id"], ["response_actions.action_id"]),
        sa.PrimaryKeyConstraint("containment_id"),
    )
    op.create_index(
        "simulated_containments_one_active",
        "simulated_containments",
        ["kind", "target"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "simulated_containments_due", "simulated_containments", ["status", "ends_at"], unique=False
    )
    op.create_index(
        "simulated_containments_by_target",
        "simulated_containments",
        ["kind", "target", "reverted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_simulated_containments_incident_id"),
        "simulated_containments",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_simulated_containments_last_incident_id"),
        "simulated_containments",
        ["last_incident_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_simulated_containments_last_incident_id"), table_name="simulated_containments"
    )
    op.drop_index(
        op.f("ix_simulated_containments_incident_id"), table_name="simulated_containments"
    )
    op.drop_index("simulated_containments_by_target", table_name="simulated_containments")
    op.drop_index("simulated_containments_due", table_name="simulated_containments")
    op.drop_index(
        "simulated_containments_one_active",
        table_name="simulated_containments",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("simulated_containments")
