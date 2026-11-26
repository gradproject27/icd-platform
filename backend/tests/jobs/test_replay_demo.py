"""Task 31 end to end on PostgreSQL: answers recorded offline from the file (no platform) are
replayed by the worker after a real upload of the same file. Every incident must find its
recording, which proves the offline packages equal the platform's; the High incident still goes
through the freeze gate. The export path is checked the same way."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analysis.replay import MODEL_PREFIX, ReplayGenerator, export_upload, record_file
from app.analysis.stub import StubGenerator
from app.contracts import AnalysisStatus
from app.response.models import AuditRow
from tests.jobs.test_analysis_job import drain, incidents

TABLES = (
    "analysis_reports, masking_maps, incident_events, incidents, audit_records, "
    "response_actions, response_windows, incident_status_history, incident_lifecycle"
)


class FakeClusterModel(StubGenerator):
    """Stands in for the 27B model: the stub's text, recorded as an hpc run."""

    generated_by, model_id = "hpc", "fake-27b"


@pytest.fixture
def engine(engine):
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    return engine


def _models_and_windows(engine):
    with Session(engine) as session:
        models = set(session.scalars(text("SELECT model_id FROM analysis_reports")))
        windows = session.scalars(
            select(AuditRow).where(AuditRow.event_type == "response_window.opened")
        ).all()
    return models, windows


def test_offline_recording_is_replayed_by_the_platform(upload, fixture_events, engine, settings):
    recording = record_file(
        "fixture", fixture_events, FakeClusterModel(), lambda: datetime.now(UTC)
    )
    upload(fixture_events.read_bytes())
    drain(engine, settings, lambda: ReplayGenerator([recording]))

    stored = incidents(engine)
    assert len(stored) == len(recording.entries)
    assert all(i.analysis_status == AnalysisStatus.SUCCEEDED for i in stored)
    models, windows = _models_and_windows(engine)
    assert models == {MODEL_PREFIX + "fake-27b"}
    assert len(windows) == 1  # the fixture's High incident, as with a live model


def test_export_from_the_platform_matches_after_reset(upload, fixture_events, engine, settings):
    first = upload(fixture_events.read_bytes())
    drain(engine, settings, FakeClusterModel)
    recording = export_upload(engine, first["upload_id"], "fixture")
    assert recording.model_id == "fake-27b" and len(recording.entries) == len(incidents(engine))

    with engine.begin() as connection:  # what the demo reset does to these tables
        connection.execute(text(f"TRUNCATE {TABLES}, jobs, uploads RESTART IDENTITY CASCADE"))
    second = upload(fixture_events.read_bytes())
    assert second["upload_id"] != first["upload_id"]
    drain(engine, settings, lambda: ReplayGenerator([recording]))

    assert all(i.analysis_status == AnalysisStatus.SUCCEEDED for i in incidents(engine))
    assert _models_and_windows(engine)[0] == {MODEL_PREFIX + "fake-27b"}
    with pytest.raises(ValueError, match="is itself a replay"):
        export_upload(engine, second["upload_id"], "fixture")
