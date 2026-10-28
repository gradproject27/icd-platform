"""Database tables of the platform (migration 0002): uploads, jobs, stored events, quarantine.

C1 owns the tables (decision D6). C2's parsers never write to them; the worker does.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Timestamp = DateTime(timezone=True)


class UploadRow(Base):
    __tablename__ = "uploads"

    upload_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Indexed for the duplicate-upload guard C2 owns in Week 4.
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    received_at: Mapped[datetime] = mapped_column(Timestamp)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('ingest', 'analysis')", name="jobs_kind"),
        CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="jobs_state"),
        Index("jobs_queue", "state", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str | None] = mapped_column(String(32))
    upload_id: Mapped[str | None] = mapped_column(
        ForeignKey("uploads.upload_id"), unique=True, index=True
    )
    # Input of an analysis job (an EvidencePackage as JSON); null for ingest jobs.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    started_at: Mapped[datetime | None] = mapped_column(Timestamp)
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp)
    # The worker that holds the job, and when it last proved it is alive (decision D8).
    worker_id: Mapped[str | None] = mapped_column(String(128))
    heartbeat_at: Mapped[datetime | None] = mapped_column(Timestamp)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class EventRow(Base):
    """One stored Event. `data` is the full contract JSON; the columns are for querying."""

    __tablename__ = "events"
    __table_args__ = (Index("events_by_label", "upload_id", "label_status", "event_id"),)

    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.upload_id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(Timestamp, index=True)
    label_status: Mapped[str] = mapped_column(String(16))
    event_type: Mapped[str] = mapped_column(Text)
    host: Mapped[str | None] = mapped_column(Text)
    src_ip: Mapped[str | None] = mapped_column(String(64))
    dst_ip: Mapped[str | None] = mapped_column(String(64))
    user: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class QuarantineRow(Base):
    __tablename__ = "quarantined_records"

    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.upload_id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_ref: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    raw_excerpt: Mapped[str | None] = mapped_column(String(500))
