"""The background worker: takes jobs from the Postgres queue and runs them.

One job at a time per worker process. While a job runs, a heartbeat thread refreshes the
job's lease, so a crashed worker's job is taken back by reap_stale (any worker runs it) and
retried or failed with worker_lost. A job always ends done or failed, never stays running.
"""

import logging
import os
import socket
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from app.api.schemas import ErrorCode, JobKind
from app.jobs.errors import JobFailure, JobLost
from app.jobs.ingest import run_ingest
from app.jobs.queue import claim_next, clear_upload_rows, fail, finish, heartbeat, reap_stale
from app.models import JobRow
from app.settings import Settings

log = logging.getLogger("icd.worker")

HEARTBEAT_FILE = Path("/tmp/worker-heartbeat")

# A runner returns the job's result: {"counts": ...} or {"analysis": ...}.
Runner = Callable[[Engine, JobRow, str, Settings, Callable[[], datetime]], dict[str, Any]]


def _ingest(engine, job, worker_id, settings, clock) -> dict[str, Any]:
    return {"counts": run_ingest(engine, job, worker_id, settings, clock)}


RUNNERS: dict[JobKind, Runner] = {JobKind.INGEST: _ingest}


def new_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def touch_heartbeat_file() -> None:
    HEARTBEAT_FILE.touch()


class _Heartbeat(threading.Thread):
    """Refreshes the job's lease every few seconds until stopped."""

    def __init__(self, engine: Engine, job_id: str, worker_id: str, settings: Settings, clock):
        super().__init__(daemon=True, name=f"heartbeat-{job_id}")
        self.engine, self.job_id, self.worker_id = engine, job_id, worker_id
        self.interval, self.clock = settings.heartbeat_seconds, clock
        self.done = threading.Event()

    def run(self) -> None:
        while not self.done.wait(self.interval):
            touch_heartbeat_file()
            try:
                if not heartbeat(self.engine, self.job_id, self.worker_id, self.clock()):
                    return
            except Exception:  # the next beat retries; the lease covers short outages
                log.warning("heartbeat for %s failed", self.job_id, exc_info=True)


def run_job(
    engine: Engine,
    job: JobRow,
    worker_id: str,
    settings: Settings,
    clock: Callable[[], datetime],
    runners: dict[JobKind, Runner] = RUNNERS,
) -> None:
    """Run one claimed job to done or failed."""
    beat = _Heartbeat(engine, job.job_id, worker_id, settings, clock)
    beat.start()
    try:
        runner = runners.get(JobKind(job.kind))
        if runner is None:
            raise JobFailure(ErrorCode.INTERNAL_ERROR, f"No runner for {job.kind} jobs.")
        result = runner(engine, job, worker_id, settings, clock)
        if not finish(engine, job.job_id, worker_id, clock(), **result):
            log.warning("job %s was taken back before it finished", job.job_id)
        else:
            log.info("job %s done", job.job_id)
    except JobLost:
        log.warning("job %s was taken back from this worker; stopping it", job.job_id)
    except Exception as exc:
        if isinstance(exc, JobFailure):
            code, message = exc.code, exc.message
            log.info("job %s failed: %s %s", job.job_id, code.value, message)
        else:
            code, message = ErrorCode.INTERNAL_ERROR, "Unexpected error; see the worker log."
            log.exception("job %s crashed", job.job_id)
        # Only the worker that still holds the job may clean up after it.
        if fail(engine, job.job_id, worker_id, clock(), code, message) and job.upload_id:
            clear_upload_rows(engine, job.upload_id)
    finally:
        beat.done.set()
        beat.join()


def run_once(
    engine: Engine,
    worker_id: str,
    settings: Settings,
    clock: Callable[[], datetime],
    runners: dict[JobKind, Runner] = RUNNERS,
) -> bool:
    """Reap stale jobs, then run the next queued job. Returns whether a job ran."""
    for job_id in reap_stale(engine, clock(), settings.lease_seconds):
        log.warning("job %s lost its worker; taken back", job_id)
    job = claim_next(engine, worker_id, clock())
    if job is None:
        return False
    log.info("job %s (%s) claimed, attempt %d", job.job_id, job.kind, job.attempts)
    run_job(engine, job, worker_id, settings, clock, runners)
    return True


def run_forever(
    engine: Engine, settings: Settings, clock: Callable[[], datetime], stop: threading.Event
) -> None:
    worker_id = new_worker_id()
    log.info("worker %s started", worker_id)
    while not stop.is_set():
        touch_heartbeat_file()
        try:
            ran = run_once(engine, worker_id, settings, clock)
        except Exception:  # database down: keep the process alive and try again
            log.exception("worker loop error")
            ran = False
        if not ran:
            stop.wait(settings.worker_poll_seconds)
