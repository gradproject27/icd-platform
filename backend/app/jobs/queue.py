"""The job queue in Postgres (decision D8): no broker, no extra service.

A worker claims the oldest queued job with SELECT ... FOR UPDATE SKIP LOCKED, so two workers
never take the same job. While it runs, the worker refreshes heartbeat_at. A running job whose
heartbeat is older than the lease is taken back by reap_stale: queued again while attempts are
left, failed with worker_lost after that. So no job stays running forever.

Every write after the claim names the worker (worker_id) and only succeeds while that worker
still holds the job, so a worker that was presumed dead cannot overwrite a newer attempt.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from app.api.schemas import ApiError, ErrorCode, Job, JobKind, JobStage, JobState
from app.models import EventRow, JobRow, QuarantineRow


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_job(
    kind: JobKind,
    *,
    now: datetime,
    max_attempts: int,
    upload_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> JobRow:
    return JobRow(
        job_id=new_id("job"),
        kind=kind.value,
        state=JobState.QUEUED.value,
        upload_id=upload_id,
        payload=payload,
        created_at=now,
        attempts=0,
        max_attempts=max_attempts,
    )


def claim_next(engine: Engine, worker_id: str, now: datetime) -> JobRow | None:
    """Take the oldest queued job, or return None when there is none."""
    with Session(engine, expire_on_commit=False) as session, session.begin():
        job = session.scalars(
            select(JobRow)
            .where(JobRow.state == JobState.QUEUED.value)
            .order_by(JobRow.created_at, JobRow.job_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if job is None:
            return None
        job.state = JobState.RUNNING.value
        job.stage = JobStage.VALIDATING.value
        job.attempts += 1
        job.started_at = job.started_at or now
        job.worker_id = worker_id
        job.heartbeat_at = now
        job.counts = None
        return job


def _update_owned(engine: Engine, job_id: str, owner: str, values: dict[str, Any]) -> bool:
    """Update a running job only if worker `owner` still holds it. Returns whether it did."""
    with engine.begin() as connection:
        result = connection.execute(
            update(JobRow)
            .where(
                JobRow.job_id == job_id,
                JobRow.worker_id == owner,
                JobRow.state == JobState.RUNNING.value,
            )
            .values(values)
        )
        return result.rowcount == 1


def heartbeat(engine: Engine, job_id: str, worker_id: str, now: datetime) -> bool:
    return _update_owned(engine, job_id, worker_id, {"heartbeat_at": now})


def set_progress(
    engine: Engine,
    job_id: str,
    worker_id: str,
    now: datetime,
    stage: JobStage,
    counts: dict[str, Any] | None = None,
) -> bool:
    values: dict[str, Any] = {"stage": stage.value, "heartbeat_at": now}
    if counts is not None:
        values["counts"] = counts
    return _update_owned(engine, job_id, worker_id, values)


def finish(
    engine: Engine,
    job_id: str,
    worker_id: str,
    now: datetime,
    *,
    counts: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
) -> bool:
    return _update_owned(
        engine,
        job_id,
        worker_id,
        {
            "state": JobState.DONE.value,
            "stage": None,
            "finished_at": now,
            "worker_id": None,
            "counts": counts,
            "analysis": analysis,
        },
    )


def fail(
    engine: Engine, job_id: str, worker_id: str, now: datetime, code: ErrorCode, message: str
) -> bool:
    return _update_owned(
        engine,
        job_id,
        worker_id,
        {
            "state": JobState.FAILED.value,
            "stage": None,
            "finished_at": now,
            "worker_id": None,
            "error_code": code.value,
            "error_message": message,
            "counts": None,
        },
    )


def clear_upload_rows(engine: Engine, upload_id: str) -> None:
    """Remove what an earlier or failed attempt stored, so a retry starts clean."""
    with engine.begin() as connection:
        connection.execute(delete(EventRow).where(EventRow.upload_id == upload_id))
        connection.execute(delete(QuarantineRow).where(QuarantineRow.upload_id == upload_id))


def reap_stale(engine: Engine, now: datetime, lease_seconds: float) -> list[str]:
    """Take back running jobs whose worker stopped sending heartbeats. Returns their IDs."""
    cutoff = now - timedelta(seconds=lease_seconds)
    reaped: list[str] = []
    with Session(engine) as session, session.begin():
        stale = session.scalars(
            select(JobRow)
            .where(JobRow.state == JobState.RUNNING.value, JobRow.heartbeat_at < cutoff)
            .with_for_update(skip_locked=True)
        ).all()
        for job in stale:
            reaped.append(job.job_id)
            job.stage = None
            job.worker_id = None
            job.counts = None
            if job.attempts < job.max_attempts:
                job.state = JobState.QUEUED.value
                continue
            job.state = JobState.FAILED.value
            job.finished_at = now
            job.error_code = ErrorCode.WORKER_LOST.value
            job.error_message = (
                f"The worker stopped during the job {job.attempts} times. "
                "Nothing from this job was kept."
            )
            if job.upload_id is not None:
                session.execute(delete(EventRow).where(EventRow.upload_id == job.upload_id))
                session.execute(
                    delete(QuarantineRow).where(QuarantineRow.upload_id == job.upload_id)
                )
    return reaped


def to_api(job: JobRow) -> Job:
    error = None
    if job.error_code is not None:
        error = ApiError(code=ErrorCode(job.error_code), message=job.error_message or "Failed.")
    return Job(
        job_id=job.job_id,
        kind=JobKind(job.kind),
        state=JobState(job.state),
        stage=JobStage(job.stage) if job.stage else None,
        upload_id=job.upload_id,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error=error,
        counts=job.counts,
        analysis=job.analysis,
    )
