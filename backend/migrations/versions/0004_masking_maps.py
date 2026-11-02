"""C2 masking map of each evidence package (C2 Week 3, T3-07, decision C2-D6)

Numbered in merge order (team plan W3-D2): the next migration after this one is 0005.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "masking_maps",
        sa.Column("package_id", sa.String(length=128), nullable=False),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('host', 'ip', 'user')", name="masking_maps_kind"),
        sa.PrimaryKeyConstraint("package_id", "token"),
    )
    op.create_index("masking_maps_by_incident", "masking_maps", ["incident_id"], unique=False)


def downgrade() -> None:
    op.drop_index("masking_maps_by_incident", table_name="masking_maps")
    op.drop_table("masking_maps")
