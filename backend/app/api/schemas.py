"""Request and response shapes of the HTTP API: upload, job and analysis (C1, Week 2), and the
incident, response-window and decision reads and writes the dashboard uses (Step 8, W3-D9).

These are API shapes, not shared data contracts: they describe what the HTTP API sends and
accepts, and they reuse the contracts (Event, AnalysisReport) where a response carries one.
docs/api-upload-jobs.md explains every endpoint with examples; the JSON Schemas in
docs/api/schemas/ are generated from this file by `python -m app.api.export`.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.contracts import (
    AuditRecord,
    Event,
    EventRole,
    Incident,
    IncidentStatus,
    LinkKey,
    ResponseAction,
    RiskLevel,
    ScenarioId,
    UserRole,
)
from app.contracts.common import Id, NonEmptyStr, UtcDatetime, _Contract
from app.incidents.key_facts import MAX_CITED

Count = Annotated[int, Field(ge=0)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Code = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")]

# Upload limits (D5). The API reads MAX_UPLOAD_MB; this is the default.
DEFAULT_MAX_UPLOAD_MB = 512
ACCEPTED_EXTENSIONS = (".csv", ".json", ".jsonl", ".log", ".txt")


class DatasetSource(StrEnum):
    """Dataset an upload belongs to. Becomes Event.provenance.dataset_id.

    The same IDs as the sources in contracts/label-mapping.json, plus `fixture` for
    synthetic test files that are already a JSON list of Events.
    """

    FIXTURE = "fixture"
    PRECINCT6 = "precinct6"
    UNSW_NB15 = "unsw-nb15"
    CIC_IDS2017 = "cic-ids2017"
    LOGHUB_BGL = "loghub-bgl"
    LOGHUB_THUNDERBIRD = "loghub-thunderbird"
    OTRF = "otrf"


class JobKind(StrEnum):
    INGEST = "ingest"
    ANALYSIS = "analysis"


class JobState(StrEnum):
    """Where a job is. done and failed are final; a job never stays running forever."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStage(StrEnum):
    """What a running job is doing now, for progress display. Set only while running."""

    VALIDATING = "validating"
    PARSING = "parsing"
    STORING = "storing"
    CORRELATING = "correlating"
    SUBMITTING = "submitting"
    WAITING_HPC = "waiting_hpc"
    COLLECTING = "collecting"


class ErrorCode(StrEnum):
    """Machine-readable reason. The first group answers a request; the second fails a job."""

    # Request errors (HTTP 4xx)
    VALIDATION_ERROR = "validation_error"
    DATASET_UNKNOWN = "dataset_unknown"
    FILE_EMPTY = "file_empty"
    FILE_TOO_LARGE = "file_too_large"
    FORMAT_NOT_ACCEPTED = "format_not_accepted"
    DUPLICATE_UPLOAD = "duplicate_upload"
    INVALID_EVIDENCE = "invalid_evidence"
    NOT_FOUND = "not_found"
    REPORT_NOT_AVAILABLE = "report_not_available"
    ORIGINAL_NOT_AVAILABLE = "original_not_available"
    NOT_AUTHENTICATED = "not_authenticated"
    NOT_AUTHORIZED = "not_authorized"
    NOT_AWAITING_DECISION = "not_awaiting_decision"
    ALREADY_DECIDED = "already_decided"
    WINDOW_EXPIRED = "window_expired"
    WINDOW_MISMATCH = "window_mismatch"
    WINDOW_OPEN = "window_open"
    # Job failures (state failed)
    NO_PARSER = "no_parser"
    PARSE_FAILED = "parse_failed"
    COUNTS_MISMATCH = "counts_mismatch"
    STORAGE_FAILED = "storage_failed"
    WORKER_LOST = "worker_lost"
    UNMASKED_EVIDENCE = "unmasked_evidence"
    HPC_UNREACHABLE = "hpc_unreachable"
    HPC_TIMEOUT = "hpc_timeout"
    HPC_JOB_FAILED = "hpc_job_failed"
    REPORT_MISSING = "report_missing"
    CORRELATION_FAILED = "correlation_failed"
    INTERNAL_ERROR = "internal_error"


class ApiError(_Contract):
    code: ErrorCode = Field(description="Machine-readable reason.")
    message: NonEmptyStr = Field(description="Plain-language reason, safe to show to the user.")


class ErrorResponse(_Contract):
    """Body of every 4xx and 5xx answer."""

    error: ApiError


class Dataset(_Contract):
    dataset_id: DatasetSource
    name: NonEmptyStr = Field(description="Display name.")
    parser_available: bool = Field(
        description="False until C2's parser for this dataset is merged. An upload is still "
        "accepted, but its job fails with no_parser."
    )


class DatasetList(_Contract):
    """GET /datasets: the choices for the upload form."""

    items: list[Dataset]
    accepted_extensions: list[NonEmptyStr] = Field(description="Lower case, with the dot.")
    max_upload_bytes: int = Field(ge=1)


class JobAccepted(_Contract):
    """202 answer of POST /analysis-jobs."""

    job_id: Id
    status_url: NonEmptyStr = Field(description="Path of GET /jobs/{job_id}, without /api.")


class UploadAccepted(JobAccepted):
    """202 answer of POST /uploads. The file is stored; processing has not started yet."""

    upload_id: Id


class Upload(_Contract):
    """GET /uploads/{upload_id}."""

    upload_id: Id
    dataset_id: DatasetSource
    filename: Annotated[str, StringConstraints(min_length=1, max_length=255)] = Field(
        description="The name the file had on the user's machine. Display only; the server "
        "never uses it as a path."
    )
    size_bytes: int = Field(ge=1)
    sha256: Sha256 = Field(description="SHA-256 of the file content, lower-case hex.")
    received_at: UtcDatetime
    job_id: Id = Field(description="The ingest job that processes this upload.")


class IntakeCounts(_Contract):
    """C2's intake summary. No record disappears: every record read is stored or quarantined."""

    records_read: Count
    events_stored: Count
    flagged: Count
    unflagged: Count
    unlabelled: Count
    quarantined: Count
    quarantined_by_reason: dict[Code, Count] = Field(
        default_factory=dict, description="Quarantined records grouped by reason code."
    )

    @model_validator(mode="after")
    def _no_record_disappears(self) -> Self:
        if self.flagged + self.unflagged + self.unlabelled != self.events_stored:
            raise ValueError("flagged + unflagged + unlabelled must equal events_stored")
        if self.events_stored + self.quarantined != self.records_read:
            raise ValueError("events_stored + quarantined must equal records_read")
        if sum(self.quarantined_by_reason.values()) != self.quarantined:
            raise ValueError("quarantined_by_reason must add up to quarantined")
        return self


class AnalysisOutcome(_Contract):
    """Result of a finished analysis job. An invalid report is a result, not a job failure."""

    incident_id: Id
    evidence_package_id: Id
    generated_by: Literal["mock", "hpc", "local"]
    report_valid: bool = Field(description="True when the report passed every check.")
    report_id: Id | None = Field(default=None, description="Set exactly when report_valid.")
    confidence: float | None = Field(
        default=None, ge=0, le=1, description="Set exactly when report_valid."
    )
    problems: list[NonEmptyStr] = Field(
        default_factory=list, description="Why the report is not valid; empty when it is."
    )

    @model_validator(mode="after")
    def _valid_has_report(self) -> Self:
        has_report = self.report_id is not None and self.confidence is not None
        if self.report_valid != has_report:
            raise ValueError("report_id and confidence are set exactly when report_valid")
        if self.report_valid == bool(self.problems):
            raise ValueError("problems must be empty exactly when report_valid")
        return self


class Job(_Contract):
    """GET /jobs/{job_id}. Poll it about once a second until state is done or failed."""

    job_id: Id
    kind: JobKind
    state: JobState
    stage: JobStage | None = Field(default=None, description="Set exactly while running.")
    upload_id: Id | None = Field(default=None, description="Set exactly for ingest jobs.")
    created_at: UtcDatetime
    started_at: UtcDatetime | None = Field(default=None, description="First time it ran.")
    finished_at: UtcDatetime | None = Field(default=None, description="Set when done or failed.")
    attempts: Count = Field(description="Runs so far; a lost worker's job is retried.")
    max_attempts: int = Field(ge=1)
    error: ApiError | None = Field(default=None, description="Set exactly when failed.")
    counts: IntakeCounts | None = Field(
        default=None,
        description="Ingest jobs: progress while running, final when done, null otherwise.",
    )
    analysis: AnalysisOutcome | None = Field(
        default=None, description="Analysis jobs: set exactly when done."
    )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        final = self.state in (JobState.DONE, JobState.FAILED)
        if (self.stage is not None) != (self.state == JobState.RUNNING):
            raise ValueError("stage is set exactly while running")
        if (self.finished_at is not None) != final:
            raise ValueError("finished_at is set exactly when done or failed")
        if self.state in (JobState.RUNNING, JobState.DONE) and self.started_at is None:
            raise ValueError("a running or done job has started_at")
        if (self.error is not None) != (self.state == JobState.FAILED):
            raise ValueError("error is set exactly when failed")
        ingest = self.kind == JobKind.INGEST
        if (self.upload_id is not None) != ingest:
            raise ValueError("upload_id is set exactly for ingest jobs")
        if not ingest and self.counts is not None:
            raise ValueError("analysis jobs have no counts")
        if ingest and self.state == JobState.DONE and self.counts is None:
            raise ValueError("a done ingest job has counts")
        if self.state in (JobState.QUEUED, JobState.FAILED) and self.counts is not None:
            raise ValueError("counts are null while queued and after a failure")
        if (self.analysis is not None) != (not ingest and self.state == JobState.DONE):
            raise ValueError("analysis is set exactly for a done analysis job")
        return self


class EventPage(_Contract):
    """GET /uploads/{upload_id}/events: Events in event_id order."""

    items: list[Event]
    next_after: Id | None = Field(
        description="Pass as ?after= for the next page; null on the last page."
    )


class QuarantinedRecord(_Contract):
    """A record that could not become an Event (FR-03), with its reason."""

    seq: int = Field(ge=1, description="Position of the record in the file, from 1.")
    record_ref: NonEmptyStr = Field(description="Row or line reference, as in Provenance.")
    reason_code: Code = Field(description="C2's reason code, for example bad_timestamp.")
    reason: NonEmptyStr = Field(description="Plain-language reason.")
    raw_excerpt: Annotated[str, StringConstraints(max_length=500)] | None = Field(
        default=None, description="Start of the original record, cut at 500 characters."
    )


class QuarantinePage(_Contract):
    """GET /uploads/{upload_id}/quarantine: quarantined records in seq order."""

    items: list[QuarantinedRecord]
    next_after: int | None = Field(
        description="Pass as ?after= for the next page; null on the last page."
    )


# ---- Incidents, response windows and decisions (Step 8; the shapes C4 proposed in #22/#23,
# adopted under W3-D9). Each incident read comes from C1's stored incidents (migration 0005)
# with the status C5's response engine tracks; nothing here computes risk or decides.


class IncidentEntities(_Contract):
    """Distinct host, user and IP values of the incident's events, flagged and context."""

    hosts: list[str] = Field(description="Sorted, unique.")
    users: list[str] = Field(description="Sorted, unique.")
    ips: list[str] = Field(description="Source and destination IPs, sorted, unique.")


class IncidentSummary(_Contract):
    """GET /incidents/{incident_id}, and one item of GET /incidents."""

    incident: Incident
    entities: IncidentEntities
    recommended_scenario_id: ScenarioId | None = Field(
        description="C5's catalogue recommendation once the analysis is recorded; else null."
    )


class IncidentList(_Contract):
    """GET /incidents: newest first event first."""

    items: list[IncidentSummary]


class IncidentEventItem(_Contract):
    """One linked event with the role and link keys from the incident."""

    event: Event
    role: EventRole
    link_keys: list[LinkKey]


class IncidentEventList(_Contract):
    """GET /incidents/{incident_id}/events: the incident's events, oldest first."""

    items: list[IncidentEventItem]


class KeyFactItem(_Contract):
    """One distinct value among the incident's flagged events, with the events it comes from."""

    value: NonEmptyStr = Field(description="The value: an attack type, host, IP, port or user.")
    event_count: int = Field(ge=1, description="Flagged events that carry the value.")
    first_seen: UtcDatetime = Field(description="Time of the first of those events, UTC.")
    event_ids: list[Id] = Field(
        min_length=1,
        max_length=MAX_CITED,
        description=f"The first of those events (at most {MAX_CITED}), oldest first.",
    )


class KeyFactPattern(_Contract):
    """A count or order marker over the flagged events (P5, patterns.toml). Flags nothing."""

    pattern_id: NonEmptyStr
    title: NonEmptyStr
    key: NonEmptyStr = Field(description="What the events share: source and attack type, or host.")
    event_ids: list[Id] = Field(min_length=2, description="The flagged events, oldest first.")
    first_seen: UtcDatetime


class IncidentKeyFacts(_Contract):
    """GET /incidents/{incident_id}/key-facts: computed by code, never by the model.

    Only flagged events count (OD-02). Internal and external addresses follow response.toml
    [network] (decision D3). Each list is ordered by first appearance, then value, and holds at
    most 20 items; `truncated` says a list was cut.
    """

    incident_id: Id
    network_config_version: NonEmptyStr = Field(
        description="response.toml config_version that split internal from external addresses."
    )
    tactics_config_version: NonEmptyStr = Field(
        description="tactics.toml config_version that mapped attack types to ATT&CK tactics."
    )
    patterns_config_version: NonEmptyStr = Field(
        description="patterns.toml config_version of the count and order markers."
    )
    first_flagged_event_id: Id = Field(description="The earliest flagged event.")
    started_at: UtcDatetime = Field(description="Time of the earliest flagged event, UTC.")
    last_flagged_event_id: Id = Field(description="The latest flagged event.")
    last_flagged_at: UtcDatetime = Field(description="Time of the latest flagged event, UTC.")
    started_on: NonEmptyStr | None = Field(
        description="Host of the earliest flagged event, else its internal destination IP."
    )
    origin_ip: NonEmptyStr | None = Field(
        description="Source IP of the earliest flagged event when it is external; else null."
    )
    flagged_event_count: int = Field(ge=1)
    context_event_count: Count
    attack_types: list[KeyFactItem] = Field(description="Dataset attack types (labels).")
    tactics: list[KeyFactItem] = Field(
        description="MITRE ATT&CK tactics ('TA0043 Reconnaissance') of those attack types, from "
        "the reviewed table tactics.toml; never chosen by the model. ATT&CK (c) MITRE."
    )
    hosts: list[KeyFactItem]
    internal_ips: list[KeyFactItem] = Field(description="Source or destination IPs, internal.")
    external_ips: list[KeyFactItem] = Field(description="Source or destination IPs, external.")
    destination_ports: list[KeyFactItem]
    accounts: list[KeyFactItem] = Field(description="User names on flagged events.")
    truncated: bool = Field(description="True when a list held more than 20 values and was cut.")
    patterns: list[KeyFactPattern] = Field(
        description="Count and order markers (P5), earliest first. Markers only: they never flag "
        "an event, infer a label or change a score."
    )


class OriginalRecord(_Contract):
    """GET /incidents/{incident_id}/events/{event_id}/original: the line the event came from."""

    event_id: Id
    record_ref: NonEmptyStr
    source_file: NonEmptyStr
    line: str = Field(description="The original line as uploaded, without its line break.")


class AuditTrail(_Contract):
    """GET /incidents/{incident_id}/audit: the incident's audit records in written order."""

    items: list[AuditRecord]


class NotificationList(_Contract):
    """GET /notifications: notification.sent audit records of every incident, newest first."""

    items: list[AuditRecord]


class ResponseWindowStatus(StrEnum):
    OPEN = "open"
    DECIDED = "decided"
    EXPIRED = "expired"


class ResponseWindow(_Contract):
    """GET /response-windows/{incident_id}: the latest window, for the countdown (spec 7)."""

    incident_id: Id
    window_id: Id
    status: ResponseWindowStatus
    started_at: UtcDatetime
    deadline_at: UtcDatetime
    server_time: UtcDatetime = Field(description="The database clock when the server answered.")
    recommended_scenario_id: ScenarioId | None


class SimulatedContainment(_Contract):
    """A simulated IP block that ends on its own (P2, containment.toml). Nothing real is blocked."""

    containment_id: Id
    kind: Literal["block_ip"] = Field(description="Only S2's simulated IP block is timed.")
    target: NonEmptyStr = Field(description="The blocked (simulated) source IP.")
    incident_id: Id = Field(description="The incident whose action started the block.")
    action_id: Id = Field(description="The action that started the block.")
    last_incident_id: Id = Field(description="The incident whose action set the current end.")
    last_action_id: Id = Field(description="The action that set the current end.")
    offence: int = Field(ge=1, description="1 for a first block; n for the n-th repeat in a row.")
    extended: Count = Field(description="How often the same IP was blocked again while blocked.")
    started_at: UtcDatetime
    ends_at: UtcDatetime = Field(description="Planned end; the worker reverts the block then.")
    status: Literal["active", "reverted"]
    reverted_at: UtcDatetime | None = Field(description="When the block ended; null while active.")
    config_version: NonEmptyStr = Field(description="containment.toml config_version used.")
    simulated: Literal[True] = Field(description="Always true: nothing real is blocked.")


class ContainmentList(_Contract):
    """GET /incidents/{incident_id}/containments: blocks it started or extended, oldest first."""

    items: list[SimulatedContainment]


class EntityRiskIncident(_Contract):
    incident_id: Id
    score: int = Field(ge=0, le=100, description="The incident's stored risk score (C3).")


class EntityRiskItem(_Contract):
    """One source-side entity: source IP, else user, else host of its flagged events."""

    entity: NonEmptyStr
    score: int = Field(ge=0, le=100, description="Rank-weighted roll-up of its incident scores.")
    level: RiskLevel = Field(description="C3's level of the roll-up score (risk.toml thresholds).")
    incident_count: int = Field(ge=1)
    incidents: list[EntityRiskIncident] = Field(description="Highest score first.")
    tactics: list[NonEmptyStr] = Field(description="Distinct ATT&CK tactic IDs, sorted.")
    flags: list[Literal["score_threshold", "tactic_threshold"]] = Field(
        description="Thresholds reached; nothing acts on them."
    )


class EntityRiskList(_Contract):
    """GET /entity-risk: the entity roll-up (P3). Read-only: never changes an incident score."""

    config_version: NonEmptyStr = Field(description="entity_risk.toml config_version.")
    tactics_config_version: NonEmptyStr = Field(description="tactics.toml config_version.")
    window_start: UtcDatetime | None = Field(description="Null when no scored incident is read.")
    window_end: UtcDatetime | None = Field(description="Latest last event of the incidents read.")
    score_threshold: int = Field(ge=0, le=100)
    tactics_threshold: int = Field(ge=1)
    items: list[EntityRiskItem] = Field(description="Highest score first, then entity.")


class ScenarioItem(_Contract):
    """One simulated scenario of the catalogue, with its display metadata (P6)."""

    scenario_id: ScenarioId
    title: NonEmptyStr = Field(description="From response.toml.")
    automatic: bool = Field(description="May the system select it at the deadline (response.toml).")
    needs: list[Literal["source_ip", "account"]] = Field(description="Targets it needs.")
    impact: Literal["low", "medium", "high"] = Field(description="From scenario_meta.toml.")
    reversible: bool
    revert: NonEmptyStr = Field(description="How the simulated effect ends, in plain words.")


class ScenarioCatalogue(_Contract):
    """GET /scenarios: the simulated catalogue v0 with display metadata. Every one is simulated."""

    config_version: NonEmptyStr = Field(description="response.toml config_version.")
    meta_version: NonEmptyStr = Field(description="scenario_meta.toml config_version.")
    items: list[ScenarioItem]


class RecentDecision(_Contract):
    """An analyst decision (decision.recorded) or a system selection at the deadline
    (scenario.selected), from the audit trail."""

    record_id: Id = Field(description="The audit record.")
    incident_id: Id
    occurred_at: UtcDatetime
    by: Literal["analyst", "system"]
    actor: NonEmptyStr
    actor_role: UserRole | None
    decision: Literal["approve", "reject", "select", "no_action", "system_selection"]
    scenario_id: ScenarioId | None
    comment: NonEmptyStr | None


class RecentDecisionList(_Contract):
    """GET /decisions/recent?hours=: decisions of the last hours (default 72), newest first."""

    hours: int = Field(ge=1, le=168)
    since: UtcDatetime
    until: UtcDatetime = Field(description="The server clock when it answered.")
    items: list[RecentDecision] = Field(description="At most 200.")


class DecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    SELECT = "select"
    NO_ACTION = "no_action"


class DecisionRequest(_Contract):
    """POST /incidents/{incident_id}/decisions."""

    decision: DecisionType
    scenario_id: ScenarioId | None = None
    window_id: Id | None = None
    comment: Annotated[str, StringConstraints(max_length=2000)] | None = None


class DecisionRecord(_Contract):
    """201 from POST /incidents/{incident_id}/decisions, and GET /incidents/{id}/decision."""

    incident_id: Id
    window_id: Id | None
    decision: DecisionType
    scenario_id: ScenarioId | None
    comment: str | None
    decided_by: NonEmptyStr
    decided_at: UtcDatetime
    incident_status: IncidentStatus
    action: ResponseAction | None = Field(
        description="The simulated action of an approve or select; null for reject, no_action."
    )


class CurrentUser(_Contract):
    """GET /me: who the API acts as. The development identity until login exists (S8-D9)."""

    user: NonEmptyStr
    role: UserRole
