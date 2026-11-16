"""Evidence packages built from incidents stored in C1's tables (migration 0005)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.contracts import Event
from app.correlation import correlate, load_config, score_incidents
from app.db import get_engine
from app.evidence import build_package
from app.evidence.models import MaskingMapRow
from app.evidence.store import (
    IncidentNotStored,
    build_and_store_for_incident,
    build_and_store_for_upload,
    load_incident_events,
    load_masking_map,
)
from app.incidents.store import store_incidents
from app.jobs.ingest import _event_row
from app.jobs.queue import new_id
from app.models import EventRow, UploadRow

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(item)
    for item in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


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
                "TRUNCATE masking_maps, incident_events, incidents, quarantined_records, events, "
                "jobs, uploads RESTART IDENTITY CASCADE"
            )
        )
    return engine


def stored(engine):
    """An upload with its events and scored incidents stored, as the ingest job leaves it."""
    upload_id = new_id("upl")
    with Session(engine) as session, session.begin():
        session.add(
            UploadRow(
                upload_id=upload_id,
                dataset_id="fixture",
                filename="events.json",
                size_bytes=1,
                sha256="0" * 64,
                received_at=NOW,
            )
        )
        session.flush()
        session.execute(EventRow.__table__.insert(), [_event_row(upload_id, e) for e in EVENTS])
    result = correlate(EVENTS, load_config(), NOW)
    incidents = score_incidents(result.incidents, EVENTS, NOW)
    store_incidents(engine, upload_id, incidents, result.config_version)
    return upload_id, incidents


def test_stored_incident_gives_the_same_package_as_in_memory(engine):
    _, incidents = stored(engine)
    for incident in incidents:
        from_db = build_and_store_for_incident(engine, incident.incident_id, NOW)
        in_memory, _ = build_package(incident, EVENTS, NOW)
        assert from_db == in_memory


def test_loader_returns_only_the_linked_events(engine):
    _, incidents = stored(engine)
    incident = incidents[0]
    loaded, events = load_incident_events(engine, incident.incident_id)
    assert loaded == incident
    assert {e.event_id for e in events} == {link.event_id for link in incident.events}


def test_map_is_stored_and_a_second_build_adds_nothing(engine):
    _, incidents = stored(engine)
    incident = incidents[0]
    package = build_and_store_for_incident(engine, incident.incident_id, NOW)
    masking_map = load_masking_map(engine, package.package_id, incident.incident_id)
    assert masking_map.tokens, "the fixture incident has hosts and IPs to mask"
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(MaskingMapRow))
    assert build_and_store_for_incident(engine, incident.incident_id, NOW) == package
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MaskingMapRow)) == before


def test_every_incident_of_an_upload_gets_a_package(engine):
    upload_id, incidents = stored(engine)
    packages = build_and_store_for_upload(engine, upload_id, NOW)
    assert sorted(p.incident_id for p in packages) == sorted(i.incident_id for i in incidents)
    assert all(p.masked for p in packages)
    assert build_and_store_for_upload(engine, new_id("upl"), NOW) == []


def test_unknown_incident_is_refused(engine):
    with pytest.raises(IncidentNotStored):
        build_and_store_for_incident(engine, "inc-unknown", NOW)
