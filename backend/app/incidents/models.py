"""C1 tables (migration 0005): stored incidents and their links to stored events.

`incidents.data` is the full Incident contract JSON, as C3's correlation built it; the other
columns are copies for querying and sorting. `incident_events` has one row per IncidentEventLink
and points at the stored event, so an incident can never link an event that is not stored.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Timestamp = DateTime(timezone=True)


class IncidentRow(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("incidents_by_upload", "upload_id", "first_event_at"),)

    incident_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.upload_id"))
    status: Mapped[str] = mapped_column(String(32))
    incident_type: Mapped[str | None] = mapped_column(Text)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str | None] = mapped_column(String(16))
    first_event_at: Mapped[datetime] = mapped_column(Timestamp)
    last_event_at: Mapped[datetime] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)
    correlation_config_version: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class IncidentEventRow(Base):
    __tablename__ = "incident_events"
    __table_args__ = (
        CheckConstraint("role IN ('flagged', 'context')", name="incident_events_role"),
        ForeignKeyConstraint(["upload_id", "event_id"], ["events.upload_id", "events.event_id"]),
        # Which incident is this event in?
        Index("incident_events_by_event", "upload_id", "event_id"),
    )

    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    upload_id: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16))
    link_keys: Mapped[list[str]] = mapped_column(JSONB)
    linked_at: Mapped[datetime] = mapped_column(Timestamp)


class RiskAssessmentRow(Base):
    """risk-v1 audit (design 9A.3, migration 0008): one row per scoring, never changed.

    Every stored score of an incident is written here, initial and final, with the versions
    behind it; UPDATE and DELETE are refused by a trigger. incidents.data holds the newest one.
    No foreign key to incidents: re-correlating an upload replaces its incidents, and the
    records of the earlier scores must stay.
    """

    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint("phase IN ('initial', 'final')", name="risk_assessments_phase"),
        Index("risk_assessments_by_incident", "incident_id", "assessment_id"),
    )

    assessment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(128))
    upload_id: Mapped[str] = mapped_column(String(128))
    phase: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(16))
    config_version: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(Timestamp)
    recorded_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
