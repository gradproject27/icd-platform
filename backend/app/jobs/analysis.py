"""The analysis job (C1, workflow steps 4 to 6): one stored incident in, one AI attempt out.

Queued at the end of every ingest job, one job per stored incident, highest risk first
(decisions F1, F2), and by POST /incidents/{id}/analysis for a re-run (F8). A job:

1. registers the incident with C5's response engine if it is not tracked yet (T01), and moves
   it to under_analysis if it is new (T02) (F5);
2. runs AI1's `analyze_incident`: C2's builder makes the masked package, the model is called
   (or the report cache answers), the answer is checked, and the report and the incident's
   analysis fields are stored;
3. hands the updated incident to the response engine (`record_analysis`): a failed analysis is
   T05 and never freezes; a valid report is T03 (freeze, response window) or T04 (F5).

Failures (F6). A model that did not answer (check X1) is not a result: the job is queued again
while attempts are left and fails with an hpc_* code after that; only then is the analysis
recorded as failed with the response engine. A report that fails the checks IS a result: the
job is done with analysis.report_valid = false.

The model backend comes from the environment (ICD_ANALYSIS_BACKEND: stub, openai_http,
hpc_batch; F3, F4). Backfill for incidents stored before this job existed:

    python -m app.jobs.analysis --backfill
"""

import argparse
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.analysis.backends import Generator, generator_from_env
from app.analysis.service import MAX_TRIES, AnalysisAttempt
from app.analysis.store import analyze_incident
from app.api.schemas import AnalysisOutcome, ErrorCode, JobKind, JobStage, JobState
from app.contracts import IncidentStatus
from app.evidence.store import IncidentNotStored, load_incident_events
from app.incidents.models import IncidentRow
from app.jobs.errors import JobFailure, JobLost, JobRetry
from app.jobs.queue import new_job, set_progress, utcnow
from app.models import JobRow
from app.response.clock import DatabaseClock
from app.response.engine import ResponseEngine
from app.settings import Settings

log = logging.getLogger("icd.analysis_job")

# Problem detail prefixes a backend may use to name its failure (app/hpc/batch.py).
_BACKEND_CODES = {
    code.value: code
    for code in (
        ErrorCode.HPC_UNREACHABLE,
        ErrorCode.HPC_TIMEOUT,
        ErrorCode.HPC_JOB_FAILED,
        ErrorCode.REPORT_MISSING,
    )
}

GeneratorFactory = Callable[[], Generator]
EngineFactory = Callable[[Engine], ResponseEngine]


def _response_engine(engine: Engine) -> ResponseEngine:
    return ResponseEngine(engine, DatabaseClock(engine))


# ---- queueing ------------------------------------------------------------------------------


def analysis_jobs_for_upload(
    engine: Engine, upload_id: str, now: datetime, max_attempts: int
) -> list[JobRow]:
    """One queued analysis job per stored incident of an upload, highest risk score first.

    The queue takes the oldest job first, so the created_at values step by a microsecond in
    risk order (ties: earliest incident first)."""
    with Session(engine) as session:
        ids = session.scalars(
            select(IncidentRow.incident_id)
            .where(IncidentRow.upload_id == upload_id)
            .order_by(
                IncidentRow.risk_score.desc().nulls_last(),
                IncidentRow.first_event_at,
                IncidentRow.incident_id,
            )
        ).all()
    return [
        new_job(
            JobKind.ANALYSIS,
            now=now + timedelta(microseconds=i),
            max_attempts=max_attempts,
            payload={"incident_id": incident_id, "force": False},
        )
        for i, incident_id in enumerate(ids)
    ]


def open_analysis_job(engine: Engine, incident_id: str) -> JobRow | None:
    """The queued or running analysis job of an incident, if there is one."""
    with Session(engine, expire_on_commit=False) as session:
        return session.scalars(
            select(JobRow)
            .where(
                JobRow.kind == JobKind.ANALYSIS.value,
                JobRow.state.in_([JobState.QUEUED.value, JobState.RUNNING.value]),
                JobRow.payload["incident_id"].astext == incident_id,
            )
            .order_by(JobRow.created_at)
            .limit(1)
        ).first()


def queue_analysis(
    engine: Engine, incident_id: str, *, force: bool, now: datetime, max_attempts: int
) -> tuple[JobRow, bool]:
    """Queue one analysis of a stored incident. An open job for it is returned instead of a
    second one (so a double click does not run the model twice). Returns (job, created)."""
    existing = open_analysis_job(engine, incident_id)
    if existing is not None:
        return existing, False
    job = new_job(
        JobKind.ANALYSIS,
        now=now,
        max_attempts=max_attempts,
        payload={"incident_id": incident_id, "force": force},
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(job)
    return job, True


def backfill(engine: Engine, now: datetime, max_attempts: int) -> list[str]:
    """Queue an analysis job for every stored incident that never had one. Returns their IDs."""
    with Session(engine) as session:
        analysed = set(
            session.scalars(
                select(JobRow.payload["incident_id"].astext).where(
                    JobRow.kind == JobKind.ANALYSIS.value
                )
            ).all()
        )
        ids = session.scalars(
            select(IncidentRow.incident_id).order_by(
                IncidentRow.risk_score.desc().nulls_last(), IncidentRow.incident_id
            )
        ).all()
    todo = [i for i in ids if i not in analysed]
    with Session(engine) as session, session.begin():
        session.add_all(
            new_job(
                JobKind.ANALYSIS,
                now=now + timedelta(microseconds=n),
                max_attempts=max_attempts,
                payload={"incident_id": incident_id, "force": False},
            )
            for n, incident_id in enumerate(todo)
        )
    return todo


# ---- running -------------------------------------------------------------------------------


def _backend_failure(attempt: AnalysisAttempt) -> tuple[ErrorCode, str] | None:
    """(code, message) when the model gave no answer at all (check X1), else None."""
    for problem in attempt.result.problems():
        if problem.check == "X1":
            prefix = problem.detail.split(":", 1)[0].strip()
            return _BACKEND_CODES.get(prefix, ErrorCode.HPC_UNREACHABLE), problem.detail
    return None


def outcome(attempt: AnalysisAttempt) -> AnalysisOutcome:
    report = attempt.result.report
    return AnalysisOutcome(
        incident_id=attempt.incident_id,
        evidence_package_id=attempt.package_id,
        generated_by=attempt.generated_by,  # type: ignore[arg-type]
        report_valid=report is not None,
        report_id=report.report_id if report else None,
        confidence=report.confidence if report else None,
        problems=[] if report else (attempt.problems() or ["analysis failed"]),
    )


def _record(response: ResponseEngine, engine: Engine, incident_id: str) -> None:
    """Hand the stored result to the response engine, if the lifecycle is waiting for one."""
    status = response.status_of(incident_id)
    if status != IncidentStatus.UNDER_ANALYSIS:
        # A forced re-run of an incident already past analysis: the new report is stored and
        # shown, but a decision or response already under way is not reopened.
        log.info("incident %s is %s; new analysis stored, lifecycle unchanged", incident_id,
                 status.value if status else None)  # fmt: skip
        return
    incident, events = load_incident_events(engine, incident_id)
    result = response.record_analysis(incident, events)
    log.info("incident %s analysed: %s, froze=%s", incident_id, result.status.value,
             result.froze)  # fmt: skip


def run_analysis_job(
    engine: Engine,
    job: JobRow,
    worker_id: str,
    settings: Settings,
    clock: Callable[[], datetime],
    *,
    generator_factory: GeneratorFactory = generator_from_env,
    engine_factory: EngineFactory = _response_engine,
) -> dict[str, Any]:
    """Run one analysis job (module docstring). Returns {"analysis": AnalysisOutcome}."""
    payload = job.payload or {}
    incident_id = payload.get("incident_id")
    if not isinstance(incident_id, str):
        raise JobFailure(ErrorCode.INTERNAL_ERROR, "The analysis job names no incident.")
    try:
        incident, _ = load_incident_events(engine, incident_id)
    except IncidentNotStored:
        raise JobFailure(
            ErrorCode.NOT_FOUND, f"Incident {incident_id} is no longer stored."
        ) from None

    response = engine_factory(engine)
    if response.status_of(incident_id) is None:
        response.register(incident)  # T01
    if response.status_of(incident_id) == IncidentStatus.NEW:
        response.start_analysis(incident_id)  # T02

    if not set_progress(engine, job.job_id, worker_id, clock(), JobStage.SUBMITTING):
        raise JobLost(job.job_id)
    generator = generator_factory()
    # A backend that builds its own prompt on the cluster cannot take the repair turn.
    tries = MAX_TRIES if getattr(generator, "accepts_messages", True) else 1
    if hasattr(generator, "on_stage"):
        generator.on_stage = lambda stage: set_progress(  # type: ignore[attr-defined]
            engine, job.job_id, worker_id, clock(), stage
        )
    attempt = analyze_incident(
        engine, incident_id, generator, clock, force=bool(payload.get("force")), max_tries=tries
    )
    if not set_progress(engine, job.job_id, worker_id, clock(), JobStage.COLLECTING):
        raise JobLost(job.job_id)

    failure = _backend_failure(attempt)
    if failure is not None:
        code, message = failure
        if job.attempts < job.max_attempts:
            raise JobRetry(message)
        _record(response, engine, incident_id)  # T05: the analysis failed for good
        raise JobFailure(code, message)

    _record(response, engine, incident_id)
    return {"analysis": outcome(attempt).model_dump(mode="json")}


def main(argv: list[str] | None = None) -> int:
    from app.db import get_engine
    from app.settings import get_settings

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="queue an analysis job for every stored incident that never had one",
    )
    args = parser.parse_args(argv)
    if not args.backfill:
        parser.print_help()
        return 2
    queued = backfill(get_engine(), utcnow(), get_settings().job_max_attempts)
    print(f"queued {len(queued)} analysis jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
