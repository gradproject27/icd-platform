"""C5 tables (migration 0003): lifecycle state, status history, response windows, simulated
actions and the append-only audit trail.

incident_lifecycle holds each incident's state until incidents themselves are stored (Week 3,
decision D1); then its status column moves onto the incidents table.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Timestamp = DateTime(timezone=True)
STATUSES = (
    "'new', 'under_analysis', 'awaiting_human_decision', 'response_in_progress', "
    "'escalated', 'resolved', 'closed'"
)


class IncidentLifecycleRow(Base):
    __tablename__ = "incident_lifecycle"
    __table_args__ = (CheckConstraint(f"status IN ({STATUSES})", name="incident_lifecycle_status"),)

    incident_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    # The host's simulated isolation state: "isolated (simulated)" when true (OD-17).
    isolated: Mapped[bool] = mapped_column(Boolean, default=False)
    target_host: Mapped[str | None] = mapped_column(Text)
    target_source_ip: Mapped[str | None] = mapped_column(String(64))
    target_account: Mapped[str | None] = mapped_column(Text)
    incident_type: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(16))
    confidence: Mapped[float | None] = mapped_column(Float)
    recommended_scenario_id: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class StatusHistoryRow(Base):
    """Every status change with time, actor and cause (FR-31)."""

    __tablename__ = "incident_status_history"

    seq: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incident_lifecycle.incident_id"), index=True
    )
    transition_id: Mapped[str] = mapped_column(String(8))
    previous_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128))
    cause: Mapped[str] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(Timestamp)


class ResponseWindowRow(Base):
    """The 60-second analyst response window (FR-43, NFR-P-09). Database time only."""

    __tablename__ = "response_windows"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'decided', 'expired')", name="response_windows_status"),
        CheckConstraint("deadline_at > started_at", name="response_windows_deadline"),
        # At most one open window per incident (precondition 4), enforced by the database too.
        Index(
            "response_windows_one_open",
            "incident_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("response_windows_due", "status", "deadline_at"),
    )

    window_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incident_lifecycle.incident_id"))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(Timestamp)
    deadline_at: Mapped[datetime] = mapped_column(Timestamp)
    recommended_scenario_id: Mapped[str | None] = mapped_column(String(2))
    closed_at: Mapped[datetime | None] = mapped_column(Timestamp)


class ResponseActionRow(Base):
    """A simulated action. `data` is the ResponseAction contract JSON."""

    __tablename__ = "response_actions"
    __table_args__ = (CheckConstraint("simulated", name="response_actions_simulated"),)

    action_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incident_lifecycle.incident_id"), index=True
    )
    window_id: Mapped[str | None] = mapped_column(ForeignKey("response_windows.window_id"))
    scenario_id: Mapped[str] = mapped_column(String(2))
    state: Mapped[str] = mapped_column(String(32))
    simulated: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class AuditRow(Base):
    """One AuditRecord (FR-35, C-14). A trigger refuses UPDATE and DELETE (decision D7)."""

    __tablename__ = "audit_records"
    __table_args__ = (Index("audit_by_incident", "incident_id", "seq"),)

    seq: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(128), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(Timestamp)
    event_type: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(128))
    actor_role: Mapped[str | None] = mapped_column(String(32))
    incident_id: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(16))
    simulated: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
