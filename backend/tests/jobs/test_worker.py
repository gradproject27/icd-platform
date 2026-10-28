import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import DatasetSource, EventPage, Job, JobStage, QuarantinePage
from app.contracts import Event
from app.ingest import registry
from app.ingest.interface import ParseError, Quarantined
from app.jobs import ingest
from app.jobs.errors import JobLost
from app.jobs.queue import claim_next, finish, reap_stale, set_progress, utcnow
from app.models import EventRow, JobRow, QuarantineRow
from app.worker.runner import run_once

FIXTURE_EVENTS = Path(__file__).resolve().parents[3] / "fixtures" / "correlation" / "events.json"


FIXTURE = json.loads(FIXTURE_EVENTS.read_text(encoding="utf-8"))


def job(client, job_id: str) -> Job:
    return Job.model_validate(client.get(f"/jobs/{job_id}").json())


def stored(engine, model, upload_id: str) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count()).select_from(model).where(model.upload_id == upload_id)
        )


def work(engine, settings, clock=utcnow, worker_id="worker-test") -> bool:
    return run_once(engine, worker_id, settings, clock)


def test_fixture_upload_runs_end_to_end(upload, client, engine, settings):
    accepted = upload(FIXTURE_EVENTS.read_bytes())
    assert work(engine, settings) is True
    assert work(engine, settings) is False  # queue empty

    done = job(client, accepted["job_id"])
    assert done.state == "done" and done.stage is None and done.attempts == 1
    assert done.counts is not None
    assert done.counts.model_dump() == {
        "records_read": 37,
        "events_stored": 37,
        "flagged": 18,
        "unflagged": 17,
        "unlabelled": 2,
        "quarantined": 0,
        "quarantined_by_reason": {},
    }

    # M2: the events are labelled, queryable and keep their link to the original record.
    base = f"/uploads/{accepted['upload_id']}/events"
    flagged = EventPage.model_validate(client.get(f"{base}?label_status=flagged&limit=500").json())
    assert len(flagged.items) == 18 and flagged.next_after is None
    assert all(event.label.status == "flagged" for event in flagged.items)
    unlabelled = EventPage.model_validate(client.get(f"{base}?label_status=unlabelled").json())
    assert all(event.label.raw_value is None for event in unlabelled.items)
    original = {event["event_id"]: event for event in FIXTURE}
    for event in flagged.items:
        assert event == Event.model_validate(original[event.event_id])


def test_event_pages_cover_every_event_once(upload, client, engine, settings):
    accepted = upload(FIXTURE_EVENTS.read_bytes())
    work(engine, settings)
    seen, after = [], None
    while True:
        query = f"/uploads/{accepted['upload_id']}/events?limit=10"
        page = client.get(query + (f"&after={after}" if after else "")).json()
        seen += [event["event_id"] for event in page["items"]]
        after = page["next_after"]
        if after is None:
            break
    assert seen == sorted(event["event_id"] for event in FIXTURE)


def test_bad_records_are_quarantined_and_counted(upload, client, engine, settings):
    good, other = FIXTURE[0], FIXTURE[1]
    no_time = {key: value for key, value in FIXTURE[2].items() if key != "timestamp"}
    content = json.dumps([good, no_time, other, good]).encode()
    accepted = upload(content, name="mixed.json")
    work(engine, settings)

    done = job(client, accepted["job_id"])
    assert done.state == "done"
    assert done.counts.records_read == 4
    assert done.counts.events_stored == 2
    assert done.counts.quarantined_by_reason == {"duplicate_event_id": 1, "invalid_event": 1}

    page = QuarantinePage.model_validate(
        client.get(f"/uploads/{accepted['upload_id']}/quarantine").json()
    )
    assert [(item.seq, item.reason_code) for item in page.items] == [
        (2, "invalid_event"),
        (4, "duplicate_event_id"),
    ]
    assert page.items[0].record_ref == "mixed.json:2"
    assert "timestamp" in page.items[0].reason


def test_dataset_without_parser_fails_with_a_reason(upload, client, engine, settings):
    accepted = upload(b"a,b\n1,2\n", name="flows.csv", dataset_id="unsw-nb15")
    work(engine, settings)
    failed = job(client, accepted["job_id"])
    assert failed.state == "failed" and failed.counts is None
    assert failed.error.code == "no_parser"
    assert "unsw-nb15" in failed.error.message


def test_unreadable_file_fails_parse_failed(upload, client, engine, settings):
    accepted = upload(b'[{"event_id": ', name="broken.json")
    work(engine, settings)
    failed = job(client, accepted["job_id"])
    assert (failed.state, failed.error.code) == ("failed", "parse_failed")
    assert "not valid JSON" in failed.error.message


def test_missing_stored_file_fails_storage_failed(upload, client, engine, settings):
    accepted = upload(b"[]")
    (settings.upload_dir / accepted["upload_id"]).unlink()
    work(engine, settings)
    assert job(client, accepted["job_id"]).error.code == "storage_failed"


def crashing_parser(after: int):
    def parse(path, context):
        for record in FIXTURE[:after]:
            yield Event.model_validate(record)
        raise RuntimeError("boom")

    return parse


def test_parser_crash_fails_internal_error_and_keeps_nothing(
    upload, client, engine, settings, monkeypatch
):
    monkeypatch.setitem(registry.PARSERS, DatasetSource.FIXTURE, crashing_parser(after=5))
    monkeypatch.setattr(ingest, "BATCH_SIZE", 2)
    accepted = upload(b"[]")
    work(engine, settings)
    failed = job(client, accepted["job_id"])
    assert (failed.state, failed.error.code) == ("failed", "internal_error")
    assert stored(engine, EventRow, accepted["upload_id"]) == 0


def test_parse_error_mid_file_keeps_nothing(upload, client, engine, settings, monkeypatch):
    def parse(path, context):
        yield Event.model_validate(FIXTURE[0])
        yield Quarantined(record_ref="x:2", reason_code="bad_timestamp", reason="bad")
        raise ParseError("The file ends in the middle of a record.")

    monkeypatch.setitem(registry.PARSERS, DatasetSource.FIXTURE, parse)
    monkeypatch.setattr(ingest, "BATCH_SIZE", 1)
    accepted = upload(b"[]")
    work(engine, settings)
    failed = job(client, accepted["job_id"])
    assert failed.error.code == "parse_failed"
    assert failed.error.message == "The file ends in the middle of a record."
    assert stored(engine, EventRow, accepted["upload_id"]) == 0
    assert stored(engine, QuarantineRow, accepted["upload_id"]) == 0


def test_parser_returning_something_else_fails(upload, client, engine, settings, monkeypatch):
    monkeypatch.setitem(registry.PARSERS, DatasetSource.FIXTURE, lambda path, ctx: iter([{}]))
    accepted = upload(b"[]")
    work(engine, settings)
    assert job(client, accepted["job_id"]).error.code == "parse_failed"


def test_progress_counts_are_published_while_running(upload, client, engine, settings, monkeypatch):
    seen: list[Job] = []

    def parse(path, context):
        for record in FIXTURE:
            yield Event.model_validate(record)
            seen.append(job(client, accepted["job_id"]))

    monkeypatch.setitem(registry.PARSERS, DatasetSource.FIXTURE, parse)
    monkeypatch.setattr(ingest, "BATCH_SIZE", 10)
    accepted = upload(b"[]")
    work(engine, settings)
    running = [j for j in seen if j.counts is not None]
    assert running and all(j.state == "running" and j.stage == "storing" for j in running)
    assert running[-1].counts.records_read == 30
    assert job(client, accepted["job_id"]).counts.records_read == 37


def test_crashed_worker_job_is_retried_from_scratch(upload, client, engine, settings):
    accepted = upload(FIXTURE_EVENTS.read_bytes())
    now = utcnow()
    # Worker A takes the job, stores part of it and dies without a word.
    dead = claim_next(engine, "worker-a", now)
    with engine.begin() as connection:
        connection.execute(
            EventRow.__table__.insert(),
            [ingest._event_row(dead.upload_id, Event.model_validate(e)) for e in FIXTURE[:5]],
        )

    # Within the lease nobody touches it.
    assert work(engine, settings, clock=lambda: now + timedelta(seconds=30)) is False
    assert job(client, accepted["job_id"]).state == "running"

    # After the lease, worker B takes it back and runs it from scratch.
    later = now + timedelta(seconds=settings.lease_seconds + 1)
    assert work(engine, settings, clock=lambda: later, worker_id="worker-b") is True
    done = job(client, accepted["job_id"])
    assert (done.state, done.attempts) == ("done", 2)
    assert done.counts.events_stored == 37
    assert stored(engine, EventRow, accepted["upload_id"]) == 37


def test_job_fails_worker_lost_after_max_attempts(upload, client, engine, settings):
    accepted = upload(FIXTURE_EVENTS.read_bytes())
    now = utcnow()
    for attempt in range(settings.job_max_attempts):
        claimed = claim_next(engine, f"worker-{attempt}", now)
        assert claimed is not None and claimed.attempts == attempt + 1
        with engine.begin() as connection:
            connection.execute(
                EventRow.__table__.insert(),
                [ingest._event_row(claimed.upload_id, Event.model_validate(FIXTURE[0]))],
            )
        now += timedelta(seconds=settings.lease_seconds + 1)
        reap_stale(engine, now, settings.lease_seconds)
        if attempt + 1 < settings.job_max_attempts:
            assert job(client, accepted["job_id"]).state == "queued"
            ingest.clear_upload_rows(engine, claimed.upload_id)

    failed = job(client, accepted["job_id"])
    assert (failed.state, failed.error.code, failed.attempts) == ("failed", "worker_lost", 3)
    assert failed.finished_at is not None
    assert stored(engine, EventRow, accepted["upload_id"]) == 0


def test_a_reaped_worker_cannot_write_any_more(upload, engine, settings):
    upload(b"[]")
    now = utcnow()
    claimed = claim_next(engine, "worker-a", now)
    reap_stale(engine, now + timedelta(seconds=settings.lease_seconds + 1), settings.lease_seconds)
    claim_next(engine, "worker-b", now)
    assert set_progress(engine, claimed.job_id, "worker-a", now, JobStage.PARSING) is False
    assert finish(engine, claimed.job_id, "worker-a", now, counts=None) is False
    with Session(engine) as session:
        assert session.get(JobRow, claimed.job_id).worker_id == "worker-b"


def test_lost_job_stops_the_ingest(upload, engine, settings, monkeypatch):
    upload(FIXTURE_EVENTS.read_bytes())
    claimed = claim_next(engine, "worker-a", utcnow())
    monkeypatch.setattr(ingest, "set_progress", lambda *args, **kwargs: False)
    with pytest.raises(JobLost):
        ingest.run_ingest(engine, claimed, "worker-a", settings, utcnow)


def test_two_workers_never_take_the_same_job(upload, engine):
    upload(b"[]")
    now = utcnow()
    first = claim_next(engine, "worker-a", now)
    assert first is not None
    assert claim_next(engine, "worker-b", now) is None


def test_jobs_run_oldest_first(upload, engine, settings):
    first, second = upload(b"[]"), upload(b"[]")
    assert claim_next(engine, "w", utcnow()).job_id == first["job_id"]
    assert claim_next(engine, "w", utcnow()).job_id == second["job_id"]
