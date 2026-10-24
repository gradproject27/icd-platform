"""EvidencePackage: what the AI receives for one incident, built by C2 (OD-03, NFR-S-07)."""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.contracts.common import (
    EventRole,
    Id,
    LabelStatus,
    NonEmptyStr,
    RiskLevel,
    UtcDatetime,
    _Contract,
)

MAX_EVIDENCE_EVENTS = 50

Summary = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class IncidentContext(_Contract):
    """Incident metadata given to the AI (OD-03)."""

    incident_type: NonEmptyStr | None = Field(
        default=None, description="Incident type; null = not classified yet."
    )
    risk_score: int | None = Field(
        default=None, ge=0, le=100, description="Deterministic risk score; null = not scored."
    )
    risk_level: RiskLevel | None = Field(default=None, description="Risk level; null = not scored.")
    first_event_at: UtcDatetime = Field(description="Timestamp of the earliest event, UTC.")
    last_event_at: UtcDatetime = Field(description="Timestamp of the latest event, UTC.")
    flagged_event_count: int = Field(ge=0, description="Flagged events in the incident.")
    context_event_count: int = Field(ge=0, description="Context events in the incident.")
    host_count: int = Field(ge=0, description="Distinct hosts in the incident.")


class EvidenceEvent(_Contract):
    """The citable view of one Event. Entity values may be masked tokens (NFR-S-07)."""

    event_id: Id = Field(description="ID of the Event; the AI cites this ID.")
    timestamp: UtcDatetime = Field(description="Event time, UTC.")
    event_type: NonEmptyStr = Field(description="Normalized event type.")
    role: EventRole = Field(description="flagged or context, as in the incident link.")
    label_status: LabelStatus = Field(description="Dataset label status of the event.")
    attack_type: NonEmptyStr | None = Field(
        default=None, description="Dataset attack type; null if absent."
    )
    host: NonEmptyStr | None = Field(
        default=None, description="Host or masked token; null if absent."
    )
    src_ip: NonEmptyStr | None = Field(
        default=None, description="Source IP or masked token; null if absent."
    )
    dst_ip: NonEmptyStr | None = Field(
        default=None, description="Destination IP or masked token; null if absent."
    )
    user: NonEmptyStr | None = Field(
        default=None, description="Account or masked token; null if absent."
    )
    summary: Summary = Field(description="Short description of the event.")
    source: NonEmptyStr = Field(description="Provenance source, for example the file name.")

    @model_validator(mode="after")
    def _role_matches_label(self) -> Self:
        if (self.role == EventRole.FLAGGED) != (self.label_status == LabelStatus.FLAGGED):
            raise ValueError(
                "a flagged event must have label_status flagged, and a context event "
                "unflagged or unlabelled"
            )
        return self


class EvidencePackage(_Contract):
    """What the AI receives for one incident (OD-03, NFR-S-07, FR-13)."""

    schema_version: Literal["1.0"] = Field(default="1.0", description="Contract version.")
    package_id: Id = Field(description="Unique package ID.")
    incident_id: Id = Field(description="ID of the incident the package describes.")
    created_at: UtcDatetime = Field(description="When the package was built, UTC.")
    incident: IncidentContext = Field(description="Incident metadata (OD-03).")
    events: list[EvidenceEvent] = Field(
        max_length=MAX_EVIDENCE_EVENTS,
        description="Up to 50 events: all flagged events first (up to the cap), then sampled "
        "context events (OD-03). Event IDs are unique.",
    )
    total_event_count: int = Field(ge=0, description="Events in the incident, before the cap.")
    truncated: bool = Field(description="True exactly when events were left out by the cap.")
    masked: bool = Field(
        default=True,
        description="True when host, user and IP values are pseudonymised as consistent "
        "tokens within the package, for example host-01 (NFR-S-07).",
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [event.event_id for event in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("event IDs in events must be unique")
        if len(self.events) > self.total_event_count:
            raise ValueError("events must not exceed total_event_count")
        if self.truncated != (len(self.events) < self.total_event_count):
            raise ValueError("truncated must be true exactly when events were left out")
        seen_context = False
        for event in self.events:
            if event.role == EventRole.CONTEXT:
                seen_context = True
            elif seen_context:
                raise ValueError("all flagged events must come before any context event")
        return self

    def citable_event_ids(self) -> frozenset[str]:
        """The event IDs a report may cite."""
        return frozenset(event.event_id for event in self.events)
