"""The confidence job (risk-v1 step 6b, design 9A.3): phase 2 of the risk score.

Queued at the end of an ingest job when ICD_CONFIDENCE_BACKEND=hpc_batch (app.confidence.hpc),
instead of the analysis jobs. Until it ends, the upload's incidents carry the phase 1 score:
each flagged event's fixed dataset C, flags confidence_fixed and llm_pending. The job:

1. writes the confidence input file of the upload (app.confidence.handoff: features and
   masked group descriptions only) and runs the HPC batch job (app.confidence.batch_run);
2. on an answer, scores the incidents again with the model's C (phase final);
3. when the cluster gives no answer, the job is tried again while attempts are left; after the
   last one, the incidents are scored again with llm_unavailable (the initial score stays the
   current one and is never shown as final, RV1-D3), and the job still ends done;
4. queues the analysis jobs (decision F1), so the AI report runs only after phase 2.

The job row holds the upload ID in its payload, not in jobs.upload_id: a failed confidence job
must never clear the upload's events and incidents the way a failed ingest job does.
"""

import logging
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.analysis.backends import BackendError
from app.api.schemas import JobKind, JobStage
from app.confidence import handoff
from app.correlation.config import load_config
from app.incidents.store import _events_that_can_matter, load_incidents, rescore_upload
from app.jobs.analysis import analysis_jobs_for_upload
from app.jobs.errors import JobLost, JobRetry
from app.jobs.queue import new_job, set_progress
from app.models import JobRow
from app.settings import Settings

log = logging.getLogger("icd.confidence_job")


def confidence_job_for_upload(upload_id: str, now: datetime, max_attempts: int) -> JobRow:
    return new_job(
        JobKind.CONFIDENCE, now=now, max_attempts=max_attempts, payload={"upload_id": upload_id}
    )


def default_batch():
    from app.confidence.hpc import ConfidenceBatch, config_from_env

    return ConfidenceBatch(config_from_env(os.environ))


def run_confidence_job(
    engine: Engine,
    job: JobRow,
    worker_id: str,
    settings: Settings,
    clock: Callable[[], datetime],
    batch_factory: Callable[[], Any] = default_batch,
) -> dict[str, Any]:
    upload_id = (job.payload or {})["upload_id"]

    def progress(stage: JobStage) -> None:
        if not set_progress(engine, job.job_id, worker_id, clock(), stage):
            raise JobLost

    config = load_config()
    incidents = load_incidents(engine, upload_id)
    with Session(engine) as session:
        events, _ = _events_that_can_matter(session, upload_id, config)
    data = handoff.build_input(job.job_id, incidents, {e.event_id: e for e in events})

    owner = (job.job_id, worker_id)
    confidences = None
    if data["events"]:
        progress(JobStage.SUBMITTING)
        try:
            batch = batch_factory()
            batch.on_stage = progress
            confidences = handoff.to_confidences(batch.submit(data))
        except (BackendError, ValueError) as exc:
            if job.attempts < job.max_attempts:
                raise JobRetry(str(exc)) from exc
            log.warning("confidence for upload %s unavailable: %s", upload_id, exc)
        if confidences is None:
            confidences = handoff.pending("llm_unavailable")
    else:  # no flagged NetFlow v3 event: no model applies; fixed C, no LLM flag
        confidences = handoff.fixed_only()
    rescore_upload(engine, upload_id, clock(), config=config, owner=owner, confidences=confidences)
    follow_up = analysis_jobs_for_upload(engine, upload_id, clock(), settings.job_max_attempts)
    return {"follow_up": follow_up}
