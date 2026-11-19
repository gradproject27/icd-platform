"""Stored reports, the database cache and the incident fields (migration 0006). Needs Postgres."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.analysis.backends import Generation
from app.analysis.models import AnalysisReportRow
from app.analysis.store import analyze_incident, latest_report, load_report
from app.analysis.stub import StubGenerator
from app.contracts import AnalysisStatus, Event, Incident
from app.correlation import correlate, load_config, score_incidents
from app.db import get_engine
from app.evidence.store import IncidentNotStored, load_masking_map, unmask_report
from app.incidents.models import IncidentRow
from app.incidents.store import store_incidents
from app.jobs.ingest import _event_row
from app.jobs.queue import delete_upload_rows, new_id
from app.models import EventRow, UploadRow
from app.response import report_valid

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(item)
    for item in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
NOW = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _needs_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")


@pytest.fixture
def engine():
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE analysis_reports, masking_maps, incident_events, incidents, "
                "quarantined_records, events, jobs, uploads RESTART IDENTITY CASCADE"
            )
        )
    return engine


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class Broken:
    generated_by = "local"
    model_id = StubGenerator.model_id  # same pin as the stub: same cache key

    def generate(self, messages, evidence):
        return Generation("not json")


def stored(engine) -> tuple[str, Incident]:
    upload_id = new_id("upl")
    with Session(engine) as session, session.begin():
        session.add(UploadRow(upload_id=upload_id, dataset_id="fixture", filename="events.json",
                              size_bytes=1, sha256="0" * 64, received_at=NOW))  # fmt: skip
        session.flush()
        session.execute(EventRow.__table__.insert(), [_event_row(upload_id, e) for e in EVENTS])
    result = correlate(EVENTS, load_config(), NOW)
    incidents = score_incidents(result.incidents, EVENTS, NOW)
    store_incidents(engine, upload_id, incidents, result.config_version)
    return upload_id, next(i for i in incidents if i.events[0].event_id == "fx-002")


def _incident(engine, incident_id: str) -> Incident:
    with Session(engine) as session:
        data = session.scalar(
            select(IncidentRow.data).where(IncidentRow.incident_id == incident_id)
        )
    return Incident.model_validate(data)


def _rows(engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(AnalysisReportRow))


def test_a_valid_analysis_is_stored_and_set_on_the_incident(engine):
    _, incident = stored(engine)
    attempt = analyze_incident(engine, incident.incident_id, StubGenerator(), Clock())
    assert attempt.valid and not attempt.cache_hit
    saved = _incident(engine, incident.incident_id)
    assert saved.analysis_status == AnalysisStatus.SUCCEEDED and report_valid(saved)
    assert saved.analysis_attempts == 1
    assert saved.latest_report_id == attempt.result.report.report_id
    assert saved.confidence == attempt.result.report.confidence
    assert latest_report(engine, incident.incident_id) == attempt.result.report
    assert load_report(engine, saved.latest_report_id).grounding is not None
    with Session(engine) as session:
        row = session.get(AnalysisReportRow, saved.latest_report_id)
        assert row.cache_key == attempt.cache_key and row.raw_output == attempt.raw_output
        assert row.tries[0]["problems"] == [] and row.generated_by == "mock"


def test_the_same_evidence_is_answered_from_the_cache(engine):
    _, incident = stored(engine)
    clock, model = Clock(), StubGenerator()
    first = analyze_incident(engine, incident.incident_id, model, clock)
    second = analyze_incident(engine, incident.incident_id, model, clock)
    assert model.calls == 1 and second.cache_hit and _rows(engine) == 1
    saved = _incident(engine, incident.incident_id)
    assert saved.latest_report_id == first.result.report.report_id
    assert saved.analysis_attempts == 2


def test_force_stores_a_new_report_under_the_same_key(engine):
    _, incident = stored(engine)
    clock, model = Clock(), StubGenerator()
    first = analyze_incident(engine, incident.incident_id, model, clock)
    forced = analyze_incident(engine, incident.incident_id, model, clock, force=True)
    assert model.calls == 2 and _rows(engine) == 2
    assert forced.cache_key == first.cache_key
    assert _incident(engine, incident.incident_id).latest_report_id == (
        forced.result.report.report_id
    )
    again = analyze_incident(engine, incident.incident_id, model, clock)
    assert again.cache_hit and again.result.report.report_id == forced.result.report.report_id


def test_a_failed_analysis_stores_nothing_and_can_never_freeze(engine):
    _, incident = stored(engine)
    clock = Clock()
    good = analyze_incident(engine, incident.incident_id, StubGenerator(), clock)
    failed = analyze_incident(engine, incident.incident_id, Broken(), clock, force=True)
    assert not failed.valid and len(failed.tries) == 2 and _rows(engine) == 1
    saved = _incident(engine, incident.incident_id)
    assert saved.analysis_status == AnalysisStatus.FAILED and not report_valid(saved)
    assert saved.confidence is None and saved.analysis_attempts == 2
    assert saved.latest_report_id == good.result.report.report_id  # history only


def test_the_stored_report_is_masked_and_un_masks_for_display(engine):
    _, incident = stored(engine)
    report = analyze_incident(engine, incident.incident_id, StubGenerator(), Clock()).result.report
    stored_text = json.dumps(load_report(engine, report.report_id).model_dump(mode="json"))
    assert "web-01" not in stored_text and "host-01" in stored_text
    shown = unmask_report(report, load_masking_map(engine, report.evidence_package_id,
                                                   report.incident_id))  # fmt: skip
    assert "web-01" in shown.summary or any("web-01" in s.description for s in shown.sequence)


def test_unknown_incident(engine):
    with pytest.raises(IncidentNotStored):
        analyze_incident(engine, "inc-missing", StubGenerator(), Clock())


def test_reports_go_with_their_upload(engine):
    upload_id, incident = stored(engine)
    analyze_incident(engine, incident.incident_id, StubGenerator(), Clock())
    with engine.begin() as connection:
        delete_upload_rows(connection, upload_id)
    assert _rows(engine) == 0
