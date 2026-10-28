"""Upload, job and stored-data endpoints (docs/api-upload-jobs.md). Week 2, C1 steps 1 and 2.

POST /uploads stores the file and queues a job, then answers 202 at once: the HTTP request
never waits for processing. The worker does the rest.
"""

from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiException
from app.api.schemas import (
    ACCEPTED_EXTENSIONS,
    Dataset,
    DatasetList,
    DatasetSource,
    ErrorCode,
    EventPage,
    Job,
    JobKind,
    QuarantinedRecord,
    QuarantinePage,
    Upload,
    UploadAccepted,
)
from app.contracts import Event, LabelStatus
from app.db import get_engine
from app.ingest.registry import DATASET_NAMES, PARSERS
from app.jobs.queue import new_id, new_job, to_api, utcnow
from app.models import EventRow, JobRow, QuarantineRow, UploadRow
from app.settings import get_settings
from app.storage import TooLarge, delete_stored, save_stream

router = APIRouter()

MAX_PAGE = 500


def display_name(raw: str | None) -> str:
    """The base name of the user's file, for display only. Never used as a path."""
    name = PurePosixPath((raw or "").replace("\\", "/")).name.strip()
    return name[:255] or "upload"


def _not_found(what: str, item_id: str) -> ApiException:
    return ApiException(404, ErrorCode.NOT_FOUND, f"No {what} with ID {item_id} exists.")


@router.get("/datasets", response_model=DatasetList)
def list_datasets() -> DatasetList:
    return DatasetList(
        items=[
            Dataset(
                dataset_id=source,
                name=DATASET_NAMES[source],
                parser_available=source in PARSERS,
            )
            for source in DatasetSource
        ],
        accepted_extensions=list(ACCEPTED_EXTENSIONS),
        max_upload_bytes=get_settings().max_upload_bytes,
    )


@router.post("/uploads", status_code=202, response_model=UploadAccepted)
async def create_upload(
    response: Response,
    file: Annotated[UploadFile, File(description="The log or dataset file.")],
    dataset_id: Annotated[str, Form(description="One of the dataset IDs from GET /datasets.")],
) -> UploadAccepted:
    settings = get_settings()
    try:
        dataset = DatasetSource(dataset_id)
    except ValueError:
        raise ApiException(
            422, ErrorCode.DATASET_UNKNOWN, f'dataset_id "{dataset_id}" is not a known dataset.'
        ) from None
    filename = display_name(file.filename)
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in ACCEPTED_EXTENSIONS:
        shown = f"Files ending in {suffix}" if suffix else "Files without an extension"
        raise ApiException(
            415,
            ErrorCode.FORMAT_NOT_ACCEPTED,
            f"{shown} are not accepted. Accepted: {', '.join(ACCEPTED_EXTENSIONS)}.",
        )

    upload_id = new_id("upl")
    limit_mb = settings.max_upload_bytes // (1024 * 1024)
    try:
        size, sha256 = await save_stream(
            file, settings.upload_dir, upload_id, settings.max_upload_bytes
        )
    except TooLarge:
        raise ApiException(
            413, ErrorCode.FILE_TOO_LARGE, f"The file is larger than the {limit_mb} MB limit."
        ) from None
    if size == 0:
        delete_stored(settings.upload_dir, upload_id)
        raise ApiException(400, ErrorCode.FILE_EMPTY, "The file is empty.")

    now = utcnow()
    job = new_job(
        JobKind.INGEST, now=now, max_attempts=settings.job_max_attempts, upload_id=upload_id
    )
    upload = UploadRow(
        upload_id=upload_id,
        dataset_id=dataset.value,
        filename=filename,
        size_bytes=size,
        sha256=sha256,
        received_at=now,
    )

    def store() -> None:
        with Session(get_engine(), expire_on_commit=False) as session, session.begin():
            session.add(upload)
            session.flush()
            session.add(job)

    try:
        await run_in_threadpool(store)
    except Exception:
        delete_stored(settings.upload_dir, upload_id)
        raise
    status_url = f"/jobs/{job.job_id}"
    response.headers["Location"] = status_url
    return UploadAccepted(upload_id=upload_id, job_id=job.job_id, status_url=status_url)


@router.get("/uploads/{upload_id}", response_model=Upload)
def get_upload(upload_id: str) -> Upload:
    with Session(get_engine()) as session:
        row = session.execute(
            select(UploadRow, JobRow.job_id)
            .join(JobRow, JobRow.upload_id == UploadRow.upload_id)
            .where(UploadRow.upload_id == upload_id)
        ).first()
    if row is None:
        raise _not_found("upload", upload_id)
    upload, job_id = row
    return Upload(
        upload_id=upload.upload_id,
        dataset_id=DatasetSource(upload.dataset_id),
        filename=upload.filename,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        received_at=upload.received_at,
        job_id=job_id,
    )


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    with Session(get_engine()) as session:
        job = session.get(JobRow, job_id)
    if job is None:
        raise _not_found("job", job_id)
    return to_api(job)


def _require_upload(session: Session, upload_id: str) -> None:
    if session.get(UploadRow, upload_id) is None:
        raise _not_found("upload", upload_id)


@router.get("/uploads/{upload_id}/events", response_model=EventPage)
def list_events(
    upload_id: str,
    label_status: LabelStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 100,
    after: str | None = None,
) -> EventPage:
    with Session(get_engine()) as session:
        _require_upload(session, upload_id)
        query = select(EventRow.event_id, EventRow.data).where(EventRow.upload_id == upload_id)
        if label_status is not None:
            query = query.where(EventRow.label_status == label_status.value)
        if after is not None:
            query = query.where(EventRow.event_id > after)
        rows = session.execute(query.order_by(EventRow.event_id).limit(limit + 1)).all()
    page = rows[:limit]
    return EventPage(
        items=[Event.model_validate(data) for _, data in page],
        next_after=page[-1].event_id if len(rows) > limit else None,
    )


@router.get("/uploads/{upload_id}/quarantine", response_model=QuarantinePage)
def list_quarantine(
    upload_id: str,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 100,
    after: Annotated[int | None, Query(ge=0)] = None,
) -> QuarantinePage:
    with Session(get_engine()) as session:
        _require_upload(session, upload_id)
        query = select(QuarantineRow).where(QuarantineRow.upload_id == upload_id)
        if after is not None:
            query = query.where(QuarantineRow.seq > after)
        rows = session.scalars(query.order_by(QuarantineRow.seq).limit(limit + 1)).all()
    page = rows[:limit]
    return QuarantinePage(
        items=[
            QuarantinedRecord(
                seq=row.seq,
                record_ref=row.record_ref,
                reason_code=row.reason_code,
                reason=row.reason,
                raw_excerpt=row.raw_excerpt,
            )
            for row in page
        ],
        next_after=page[-1].seq if len(rows) > limit else None,
    )
