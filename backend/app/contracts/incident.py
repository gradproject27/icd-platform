"""Incident: a group of related events, built by C3's correlation (FR-07, FR-08, FR-31)."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.contracts.common import (
    EventRole,
    Id,
    NonEmptyStr,
    RiskLevel,
    UtcDatetime,
    _Contract,
)

Fraction = Annotated[float, Field(ge=0, le=1)]


class IncidentStatus(StrEnum):
    """Lifecycle state (FR-31, TD-11). new replaces the former name Detected."""

    NEW = "new"
    UNDER_ANALYSIS = "under_analysis"
    AWAITING_HUMAN_DECISION = "awaiting_human_decision"
    RESPONSE_IN_PROGRESS = "response_in_progress"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"

    @property
    def label(self) -> str:
        """Display name, as written in the response workflow spec, section 2."""
        return _STATUS_LABELS[self]


_STATUS_LABELS = {
    IncidentStatus.NEW: "New",
    IncidentStatus.UNDER_ANALYSIS: "Under Analysis",
    IncidentStatus.AWAITING_HUMAN_DECISION: "Awaiting Human Decision",
    IncidentStatus.RESPONSE_IN_PROGRESS: "Response in Progress",
    IncidentStatus.ESCALATED: "Escalated",
    IncidentStatus.RESOLVED: "Resolved",
    IncidentStatus.CLOSED: "Closed",
}


class AnalysisStatus(StrEnum):
    """Status of the AI analysis. Analysis failed is a status, not a lifecycle state (OD-09)."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LinkKey(StrEnum):
    """The entity key that linked an event to the incident (NFR-SF-05)."""

    HOST = "host"
    IP_PAIR = "ip_pair"
    USER = "user"


class IncidentEventLink(_Contract):
    """Link from an incident to one event (FR-08)."""

    event_id: Id = Field(description="ID of the linked Event.")
    role: EventRole = Field(
        description="flagged, or context: an unflagged or unlabelled event that shares an "
        "entity in the window (OD-02). A context event is never treated as malicious."
    )
    link_keys: list[LinkKey] = Field(
        description="Keys that linked the event. Empty only for the event that started the "
        "incident."
    )
    linked_at: UtcDatetime = Field(description="When the event was linked, UTC.")


class RiskFactor(_Contract):
    """One factor of the deterministic risk score."""

    name: NonEmptyStr = Field(description="Factor name from the risk configuration.")
    value: Fraction = Field(description="Normalized factor value, 0 to 1.")
    weight: float = Field(ge=0, description="Weight of the factor in the configuration.")
    contribution: float = Field(description="Points this factor adds to the score.")
    reason: NonEmptyStr | None = Field(
        default=None,
        description="Plain-language reason for the factor's value (contracts 1.1, additive).",
    )


class RiskFlag(StrEnum):
    """Something the score had to assume because the data does not say (contracts 1.1)."""

    ASSET_UNKNOWN = "asset_unknown"
    OUTCOME_UNKNOWN = "outcome_unknown"
    SEVERITY_DEFAULT = "severity_default"


class RiskContributor(_Contract):
    """One evidence group behind the score: its strongest event (contracts 1.1)."""

    technique: NonEmptyStr = Field(description="Attack type of the group; unknown when missing.")
    entity: NonEmptyStr = Field(description="Source-side entity of the group, or none.")
    strength: Fraction = Field(description="Strength of the group's strongest event, 0 to 1.")
    event_id: Id = Field(description="ID of the group's strongest flagged event.")
    reason: NonEmptyStr = Field(description="Plain-language reason for the strength.")


class RiskAssessment(_Contract):
    """Deterministic risk score computed by C3 code, never by the LLM (OD-04, OD-05, FR-18)."""

    score: int = Field(ge=0, le=100, description="Risk score as a percentage (FR-18).")
    level: RiskLevel = Field(
        description="Level from the configurable thresholds (FR-20); enforced by C3's scoring "
        "code, not by this contract."
    )
    factors: list[RiskFactor] = Field(min_length=1, description="Per-factor breakdown (FR-19).")
    config_version: NonEmptyStr = Field(
        description="Version of the weights and thresholds file used."
    )
    computed_at: UtcDatetime = Field(description="When the score was computed, UTC.")
    likelihood: Fraction | None = Field(
        default=None, description="Combined evidence strength L, 0 to 1 (contracts 1.1)."
    )
    impact: Fraction | None = Field(
        default=None, description="Asset impact I, 0 to 1 (contracts 1.1)."
    )
    flags: list[RiskFlag] = Field(
        default_factory=list, description="Assumptions the score made (contracts 1.1)."
    )
    top_contributors: list[RiskContributor] = Field(
        default_factory=list,
        max_length=3,
        description="The strongest evidence groups, strongest first (contracts 1.1).",
    )


class Incident(_Contract):
    """A group of related events (FR-07, FR-08, FR-11, FR-18 to FR-20, FR-31, FR-42)."""

    schema_version: Literal["1.0"] = Field(default="1.0", description="Contract version.")
    incident_id: Id = Field(description="Unique incident ID.")
    status: IncidentStatus = Field(
        default=IncidentStatus.NEW, description="Lifecycle state (FR-31, TD-11)."
    )
    incident_type: NonEmptyStr | None = Field(
        default=None,
        description="C3 classification, read by C5's scenario lookup (OD-20); null = not "
        "classified yet.",
    )
    created_at: UtcDatetime = Field(description="When the incident was created, UTC.")
    updated_at: UtcDatetime = Field(description="Last change, UTC; not before created_at.")
    first_event_at: UtcDatetime = Field(description="Timestamp of the earliest event, UTC.")
    last_event_at: UtcDatetime = Field(
        description="Timestamp of the latest event, UTC; not before first_event_at."
    )
    events: list[IncidentEventLink] = Field(
        min_length=1, description="Linked events (FR-08); event IDs are unique."
    )
    risk: RiskAssessment | None = Field(
        default=None, description="Deterministic risk assessment; null = not scored yet."
    )
    analysis_status: AnalysisStatus = Field(
        default=AnalysisStatus.NOT_STARTED, description="Status of the AI analysis (OD-09)."
    )
    analysis_attempts: int = Field(default=0, ge=0, description="Number of analysis attempts.")
    latest_report_id: Id | None = Field(
        default=None,
        description="ID of the latest valid AnalysisReport; required when analysis succeeded.",
    )
    confidence: Fraction | None = Field(
        default=None,
        description="Confidence of the latest valid analysis (OD-16); set exactly when "
        "analysis succeeded (FR-42).",
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
        if self.last_event_at < self.first_event_at:
            raise ValueError("last_event_at must not be before first_event_at")
        ids = [link.event_id for link in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("event IDs in events must be unique")
        if not any(link.role == EventRole.FLAGGED for link in self.events):
            raise ValueError("an incident needs at least one flagged event")
        if sum(1 for link in self.events if not link.link_keys) > 1:
            raise ValueError("only the event that started the incident may have no link_keys")
        succeeded = self.analysis_status == AnalysisStatus.SUCCEEDED
        if (self.confidence is not None) != succeeded:
            raise ValueError("confidence must be set exactly when analysis_status is succeeded")
        if succeeded and self.latest_report_id is None:
            raise ValueError("latest_report_id is required when analysis_status is succeeded")
        return self
