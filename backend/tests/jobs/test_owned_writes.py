import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import DatasetSource, Job
from app.contracts import Event
from app.jobs import ingest
from app.jobs.errors import JobLost
from app.jobs.queue import claim_next, reap_stale, utcnow
from app.models import EventRow
from app.worker.runner import run_once

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "fixtures" / "correlation" / "events.json").read_text(
        encoding="utf-8"
    )
)


def stored(engine, upload_id: str) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(EventRow).where(EventRow.upload_id == upload_id)
        )


def take_over(engine, settings) -> None:
    """The lease runs out for worker-a and worker-b claims the job."""
    later = utcnow() + timedelta(seconds=settings.lease_seconds + 1)
    reap_stale(engine, later, settings.lease_seconds)
    assert claim_next(engine, "worker-b", later) is not None


def test_a_reaped_worker_writes_no_more_event_batches(upload, engine, settings, monkeypatch):
    accepted = upload(json.dumps(FIXTURE).encode())
    claimed = claim_next(engine, "worker-a", utcnow())

    def parse(path, context):
        for index, record in enumerate(FIXTURE[:4]):
            if index == 2:
                # worker-a stalls after its first batch was written and its progress saved.
                take_over(engine, settings)
            yield Event.model_validate(record)

    monkeypatch.setattr(ingest, "BATCH_SIZE", 2)
    with pytest.raises(JobLost):
        ingest.run_ingest(
            engine, claimed, "worker-a", settings, utcnow, {DatasetSource.FIXTURE: parse}
        )
    assert stored(engine, accepted["upload_id"]) == 2


def test_a_reaped_worker_cannot_clear_the_new_attempt(upload, engine, settings):
    accepted = upload(json.dumps(FIXTURE).encode())
    claimed = claim_next(engine, "worker-a", utcnow())
    take_over(engine, settings)
    with engine.begin() as connection:
        connection.execute(
            EventRow.__table__.insert(),
            [ingest._event_row(accepted["upload_id"], Event.model_validate(FIXTURE[0]))],
        )
    with pytest.raises(JobLost):
        ingest.run_ingest(engine, claimed, "worker-a", settings, utcnow)
    assert stored(engine, accepted["upload_id"]) == 1


def test_the_new_attempt_ends_with_its_own_counts(upload, client, engine, settings, monkeypatch):
    accepted = upload(json.dumps(FIXTURE).encode())
    claimed = claim_next(engine, "worker-a", utcnow())
    monkeypatch.setattr(ingest, "BATCH_SIZE", 2)

    def parse(path, context):
        yield Event.model_validate(FIXTURE[0])
        yield Event.model_validate(FIXTURE[1])
        take_over(engine, settings)
        yield Event.model_validate(FIXTURE[2])
        yield Event.model_validate(FIXTURE[3])

    with pytest.raises(JobLost):
        ingest.run_ingest(
            engine, claimed, "worker-a", settings, utcnow, {DatasetSource.FIXTURE: parse}
        )
    # worker-b stops too; the third attempt runs the job with the real parser.
    later = utcnow() + timedelta(seconds=3 * settings.lease_seconds)
    reap_stale(engine, later, settings.lease_seconds)
    run_once(engine, "worker-c", settings, lambda: later)
    done = Job.model_validate(client.get(f"/jobs/{accepted['job_id']}").json())
    assert done.state == "done", done.error
    assert done.counts.events_stored == len(FIXTURE)
    assert stored(engine, accepted["upload_id"]) == len(FIXTURE)
