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
