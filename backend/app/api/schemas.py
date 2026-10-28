"""Request and response shapes of the upload, job and analysis endpoints (C1, Week 2).

These are API shapes, not shared data contracts: they describe what the HTTP API sends and
accepts, and they reuse the contracts (Event, AnalysisReport) where a response carries one.
docs/api-upload-jobs.md explains every endpoint with examples; the JSON Schemas in
docs/api/schemas/ are generated from this file by `python -m app.api.export`.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.contracts import Event
from app.contracts.common import Id, NonEmptyStr, UtcDatetime, _Contract

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
    INVALID_EVIDENCE = "invalid_evidence"
    NOT_FOUND = "not_found"
    REPORT_NOT_AVAILABLE = "report_not_available"
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
