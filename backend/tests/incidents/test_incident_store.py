import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts import Event
from app.correlation.config import load_config
from app.correlation.engine import correlate
from app.correlation.risk import load_risk_config, score_incidents
from app.incidents.models import IncidentEventRow, IncidentRow
from app.incidents.store import (
    IncidentConflict,
    MissingEvents,
    _events_that_can_matter,
    correlate_upload,
    load_incident,
    load_incidents,
    rescore_upload,
    store_incidents,
)
from app.jobs.ingest import _event_row
from app.jobs.queue import clear_upload_rows, new_id
from app.models import EventRow, UploadRow

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(item)
    for item in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
EXPECTED = json.loads((FIXTURES / "expected-incidents.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def stored_upload(engine, events=EVENTS) -> str:
    """An upload whose events are stored, as the ingest worker leaves it."""
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
        session.execute(EventRow.__table__.insert(), [_event_row(upload_id, e) for e in events])
    return upload_id


def count(engine, model) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def test_stored_incidents_read_back_equal(engine):
    upload_id = stored_upload(engine)
    result = correlate(EVENTS, load_config(), NOW)
    assert store_incidents(engine, upload_id, result.incidents, result.config_version) == len(
        result.incidents
    )
    assert load_incidents(engine, upload_id) == sorted(
        result.incidents, key=lambda i: (i.first_event_at, i.incident_id)
    )
    first = result.incidents[0]
    assert load_incident(engine, first.incident_id) == first
    assert load_incident(engine, "inc-unknown") is None


def test_every_event_link_is_a_row_with_its_role(engine):
    upload_id = stored_upload(engine)
    result = correlate(EVENTS, load_config(), NOW)
    store_incidents(engine, upload_id, result.incidents, result.config_version)
    links = sum(len(i.events) for i in result.incidents)
    assert count(engine, IncidentEventRow) == links
    with Session(engine) as session:
        roles = dict(
            session.execute(
                select(IncidentEventRow.role, func.count()).group_by(IncidentEventRow.role)
            ).all()
        )
        row = session.get(IncidentRow, result.incidents[0].incident_id)
    assert roles["flagged"] == sum(
        1 for i in result.incidents for link in i.events if link.role.value == "flagged"
    )
    assert row.upload_id == upload_id
    assert row.correlation_config_version == result.config_version


def test_correlate_upload_matches_the_c3_fixture(engine):
    upload_id = stored_upload(engine)
    incidents = correlate_upload(engine, upload_id, NOW)
    assert len(incidents) == len(EXPECTED["incidents"])
    assert count(engine, IncidentRow) == len(EXPECTED["incidents"])


def test_storing_again_replaces_instead_of_duplicating(engine):
    upload_id = stored_upload(engine)
    correlate_upload(engine, upload_id, NOW)
    before = (count(engine, IncidentRow), count(engine, IncidentEventRow))
    later = datetime(2026, 11, 16, tzinfo=UTC)
    correlate_upload(engine, upload_id, later)
    assert (count(engine, IncidentRow), count(engine, IncidentEventRow)) == before
    assert all(i.created_at == later for i in load_incidents(engine, upload_id))


def test_unknown_event_stores_nothing(engine):
    result = correlate(EVENTS, load_config(), NOW)
    linked = result.incidents[0].events[0].event_id
    upload_id = stored_upload(engine, [e for e in EVENTS if e.event_id != linked])
    with pytest.raises(MissingEvents, match=linked):
        store_incidents(engine, upload_id, result.incidents, result.config_version)
    assert count(engine, IncidentRow) == count(engine, IncidentEventRow) == 0


def test_same_incident_id_from_another_upload_is_refused(engine):
    result = correlate(EVENTS, load_config(), NOW)
    first = stored_upload(engine)
    store_incidents(engine, first, result.incidents, result.config_version)
    second = stored_upload(engine)
    with pytest.raises(IncidentConflict):
        store_incidents(engine, second, result.incidents, result.config_version)
    assert load_incidents(engine, second) == []


def test_the_same_events_in_two_uploads_give_separate_incidents(engine):
    first = correlate_upload(engine, stored_upload(engine), NOW)
    again = correlate_upload(engine, (second := stored_upload(engine)), NOW)
    assert {i.incident_id for i in first}.isdisjoint(i.incident_id for i in again)
    assert len(first) == len(again) == len(EXPECTED["incidents"])
    # Deterministic per upload: correlating the same upload again gives the same IDs.
    assert [i.incident_id for i in correlate_upload(engine, second, NOW)] == [
        i.incident_id for i in again
    ]


def test_database_refuses_a_link_to_a_missing_event(engine):
    upload_id = stored_upload(engine)
    correlate_upload(engine, upload_id, NOW)
    incident_id = load_incidents(engine, upload_id)[0].incident_id
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text("INSERT INTO incident_events VALUES (:i, 'nope', :u, 'context', '[]', now())"),
            {"i": incident_id, "u": upload_id},
        )


def test_clearing_an_upload_removes_its_incidents(engine):
    upload_id = stored_upload(engine)
    correlate_upload(engine, upload_id, NOW)
    clear_upload_rows(engine, upload_id)
    assert count(engine, IncidentRow) == count(engine, IncidentEventRow) == 0
    assert count(engine, EventRow) == 0


def test_no_incidents_is_fine(engine):
    assert store_incidents(engine, stored_upload(engine), [], "v") == 0


# --- C3 Week 3, Step 3 (decisions D1 and D7 of 16 Nov 2026) --------------------------------


def _noise(n: int) -> list[Event]:
    """Unflagged events on IP pairs no flagged event uses: they can never become context. Some
    are hours later than the fixture, so they move the risk score's clock W."""
    template = next(e for e in EVENTS if e.label.status.value == "unflagged")
    return [
        template.model_copy(
            update={
                "event_id": f"noise-{k:04d}",
                "timestamp": template.timestamp + timedelta(hours=k % 13),
                "src_ip": f"192.0.2.{k % 200 + 1}",
                "dst_ip": "192.0.2.250",
                "host": None,
                "user": None,
            }
        )
        for k in range(n)
    ]


def test_every_stored_incident_has_its_risk(engine):
    upload_id = stored_upload(engine)
    incidents = correlate_upload(engine, upload_id, NOW)
    assert all(i.risk is not None for i in incidents)
    with Session(engine) as session:
        rows = session.execute(select(IncidentRow.risk_score, IncidentRow.risk_level)).all()
    assert all(score is not None and level is not None for score, level in rows)
    assert load_incidents(engine, upload_id) == sorted(
        incidents, key=lambda i: (i.first_event_at, i.incident_id)
    )


def test_stored_result_equals_correlating_every_event(engine):
    events = EVENTS + _noise(300)
    upload_id = stored_upload(engine, events)
    stored = correlate_upload(engine, upload_id, NOW)
    result = correlate(events, load_config(), NOW, scope=upload_id)
    expected = score_incidents(result.incidents, events, NOW)
    assert [i.model_dump() for i in stored] == [i.model_dump() for i in expected]


def test_only_events_that_can_matter_are_loaded(engine):
    upload_id = stored_upload(engine, EVENTS + _noise(300))
    with Session(engine) as session:
        loaded, reference = _events_that_can_matter(session, upload_id, load_config())
    ids = {e.event_id for e in loaded}
    assert not any(i.startswith("noise-") for i in ids)
    assert {e.event_id for e in EVENTS if e.label.status.value == "flagged"} <= ids
    assert reference == max(e.timestamp for e in EVENTS + _noise(300))


def test_rescoring_changes_only_the_risk(engine):
    upload_id = stored_upload(engine)
    before = correlate_upload(engine, upload_id, NOW)
    stricter = replace(load_risk_config(), unknown_impact=0.33)
    after = rescore_upload(engine, upload_id, NOW, risk=stricter)
    assert [i.incident_id for i in after] == [
        i.incident_id for i in sorted(before, key=lambda i: (i.first_event_at, i.incident_id))
    ]
    assert sum(i.risk.score for i in after) < sum(i.risk.score for i in before)
    strip = lambda i: i.model_dump(exclude={"risk"})  # noqa: E731
    assert sorted(map(str, map(strip, after))) == sorted(map(str, map(strip, before)))
    assert [i.risk for i in load_incidents(engine, upload_id)] == [i.risk for i in after]


def test_rescoring_an_upload_without_incidents_does_nothing(engine):
    assert rescore_upload(engine, stored_upload(engine, _noise(3)), NOW) == []
