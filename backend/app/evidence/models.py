"""C2 table (migration 0004): the masking map of each evidence package (T3-07, C2-D6).

One row per token of one package. The map is keyed by package, not by incident: an incident
that grows gets a new package whose tokens may be numbered differently, and a report is always
un-masked with the map of the package it was written from (AnalysisReport.evidence_package_id).
The real values stay in the app database, next to the events they come from; they never go to
the HPC.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MaskingMapRow(Base):
    __tablename__ = "masking_maps"
    __table_args__ = (
        CheckConstraint("kind IN ('host', 'ip', 'user')", name="masking_maps_kind"),
        Index("masking_maps_by_incident", "incident_id"),
    )

    package_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(8))
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
