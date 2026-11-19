"""AI1 table (migration 0006): the stored AI reports, which are also the report cache.

One row per valid report. `report` is the full AnalysisReport contract JSON, stored masked as the
model wrote it (C2-D7: the API un-masks it for display only); the other columns are copies for
lookup. `cache_key` is not unique: a forced re-analysis stores a new report under the same key,
and the cache returns the newest. A failed analysis stores no row: it is recorded on the
incident (analysis_status failed, no confidence) and in the job result.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

Timestamp = DateTime(timezone=True)


class AnalysisReportRow(Base):
    __tablename__ = "analysis_reports"
    __table_args__ = (
        CheckConstraint(
            "generated_by IN ('mock', 'hpc', 'local')", name="analysis_reports_generated_by"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="analysis_reports_confidence"),
        Index("analysis_reports_by_key", "cache_key", "created_at"),
        Index("analysis_reports_by_incident", "incident_id", "created_at"),
    )

    report_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id", ondelete="CASCADE")
    )
    evidence_package_id: Mapped[str] = mapped_column(String(128))
    cache_key: Mapped[str] = mapped_column(String(64))
    generated_by: Mapped[str] = mapped_column(String(16))
    model_id: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The model's answer as returned (masked); kept for the grounding review and the thesis.
    raw_output: Mapped[str | None] = mapped_column(Text)
    # Each model call: problems found, seconds, tokens (service.Try.record); [] for the stub.
    tries: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
