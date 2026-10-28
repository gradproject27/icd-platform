"""Ingest job: run the dataset's parser over the stored file and store what it yields.

Every record the parser yields is counted and stored, either as an Event or as a quarantined
record, so the intake summary always matches the tables (docs/api-upload-jobs.md section 4).
A duplicate event_id within one upload is quarantined, never dropped.
"""

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, func, insert, select
from sqlalchemy.orm import Session

from app.api.schemas import DatasetSource, ErrorCode, IntakeCounts, JobStage
from app.contracts import Event
from app.ingest.interface import IntakeContext, ParseError, Parser, Quarantined
from app.ingest.registry import PARSERS
from app.jobs.errors import JobFailure, JobLost
from app.jobs.queue import clear_upload_rows, set_progress
from app.models import EventRow, JobRow, QuarantineRow, UploadRow
from app.settings import Settings

BATCH_SIZE = 1000


def _event_row(upload_id: str, event: Event) -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "event_id": event.event_id,
        "dataset_id": event.provenance.dataset_id,
        "timestamp": event.timestamp,
        "label_status": event.label.status.value,
        "event_type": event.event_type,
        "host": event.host,
        "src_ip": str(event.src_ip) if event.src_ip is not None else None,
        "dst_ip": str(event.dst_ip) if event.dst_ip is not None else None,
        "user": event.user,
        "data": event.model_dump(mode="json"),
    }


def _has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(key) or _has_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_nul(item) for item in value)
    return False


class _Intake:
    def __init__(self, upload_id: str) -> None:
        self.upload_id = upload_id
        self.records_read = 0
        self.labels: Counter[str] = Counter()
        self.reasons: Counter[str] = Counter()
        self.seen: set[str] = set()
        self.events: list[dict[str, Any]] = []
        self.quarantine: list[dict[str, Any]] = []

    def add(self, item: Event | Quarantined) -> None:
        self.records_read += 1
        if isinstance(item, Event) and _has_nul(item.model_dump(mode="json")):
            # PostgreSQL text and JSONB cannot hold NUL; one such record must not fail the job.
            item = Quarantined(
                record_ref=item.provenance.record_ref,
                reason_code="nul_character",
                reason="The record contains a NUL character, which cannot be stored.",
            )
        if isinstance(item, Event) and item.event_id in self.seen:
            item = Quarantined(
                record_ref=item.provenance.record_ref,
                reason_code="duplicate_event_id",
                reason=f"event_id {item.event_id} appeared earlier in this file.",
            )
        if isinstance(item, Event):
            self.seen.add(item.event_id)
            self.labels[item.label.status.value] += 1
            self.events.append(_event_row(self.upload_id, item))
        elif isinstance(item, Quarantined):
            self.reasons[item.reason_code] += 1
            self.quarantine.append(
                {
                    "upload_id": self.upload_id,
                    "seq": self.records_read,
                    "record_ref": item.record_ref,
                    "reason_code": item.reason_code,
                    "reason": item.reason,
                    "raw_excerpt": item.raw_excerpt,
                }
            )
        else:
            raise JobFailure(
                ErrorCode.PARSE_FAILED,
                f"The parser returned a {type(item).__name__}, not an Event or a quarantined "
                "record.",
            )

    def pending(self) -> int:
        return len(self.events) + len(self.quarantine)

    def flush(self, engine: Engine) -> None:
        with engine.begin() as connection:
            if self.events:
                connection.execute(insert(EventRow), self.events)
            if self.quarantine:
                connection.execute(insert(QuarantineRow), self.quarantine)
        self.events.clear()
        self.quarantine.clear()

    def counts(self) -> dict[str, Any]:
        stored = sum(self.labels.values())
        return {
            "records_read": self.records_read,
            "events_stored": stored,
            "flagged": self.labels["flagged"],
            "unflagged": self.labels["unflagged"],
            "unlabelled": self.labels["unlabelled"],
            "quarantined": sum(self.reasons.values()),
            "quarantined_by_reason": dict(sorted(self.reasons.items())),
        }


def run_ingest(
    engine: Engine,
    job: JobRow,
    worker_id: str,
    settings: Settings,
    clock: Callable[[], datetime],
    parsers: dict[DatasetSource, Parser] = PARSERS,
) -> dict[str, Any]:
    """Process one upload. Returns the final counts, or raises JobFailure or JobLost."""
    assert job.upload_id is not None
    with Session(engine) as session:
        upload = session.get(UploadRow, job.upload_id)
    if upload is None:
        raise JobFailure(ErrorCode.STORAGE_FAILED, "The upload record is missing.")

    def progress(stage: JobStage, counts: dict[str, Any] | None = None) -> None:
        if not set_progress(engine, job.job_id, worker_id, clock(), stage, counts):
            raise JobLost

    clear_upload_rows(engine, upload.upload_id)
    path = settings.upload_dir / upload.upload_id
    if not path.is_file():
        raise JobFailure(ErrorCode.STORAGE_FAILED, "The stored file is missing.")
    parser = parsers.get(DatasetSource(upload.dataset_id))
    if parser is None:
        raise JobFailure(
            ErrorCode.NO_PARSER,
            f"No parser is available for dataset {upload.dataset_id} yet. "
            "The file is stored; nothing was ingested.",
        )

    progress(JobStage.PARSING)
    context = IntakeContext(
        upload_id=upload.upload_id,
        dataset_id=upload.dataset_id,
        source_file=upload.filename,
        ingested_at=clock(),
    )
    intake = _Intake(upload.upload_id)
    try:
        for item in parser(path, context):
            intake.add(item)
            if intake.pending() >= BATCH_SIZE:
                intake.flush(engine)
                progress(JobStage.STORING, intake.counts())
    except ParseError as exc:
        raise JobFailure(ErrorCode.PARSE_FAILED, str(exc)) from exc
    progress(JobStage.STORING)
    intake.flush(engine)

    counts = intake.counts()
    try:
        IntakeCounts.model_validate(counts)
    except ValidationError as exc:
        raise JobFailure(ErrorCode.COUNTS_MISMATCH, "The intake counts do not add up.") from exc
    with Session(engine) as session:
        stored = session.scalar(
            select(func.count()).select_from(EventRow).where(EventRow.upload_id == upload.upload_id)
        )
        quarantined = session.scalar(
            select(func.count())
            .select_from(QuarantineRow)
            .where(QuarantineRow.upload_id == upload.upload_id)
        )
    if (stored, quarantined) != (counts["events_stored"], counts["quarantined"]):
        raise JobFailure(
            ErrorCode.COUNTS_MISMATCH,
            f"Counted {counts['events_stored']} events and {counts['quarantined']} quarantined "
            f"records, but the database holds {stored} and {quarantined}.",
        )
    return counts
