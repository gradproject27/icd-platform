"""The dashboard's incident, window and decision endpoints on PostgreSQL (Step 8, W3-D9).

C3's correlation and risk score over the fixture are stored as C1 stores them, and C5's engine
runs on a FakeClock injected through the `response_engine` dependency, so no test waits.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.incidents import _window_events, response_engine
from app.contracts import AnalysisStatus, AuditEventType, Event, Incident, IncidentStatus
from app.correlation import correlate, load_config, load_risk_config, score_incidents
from app.db import get_engine
from app.incidents.store import store_incidents
from app.jobs.ingest import _event_row
from app.jobs.queue import new_id
from app.main import app
from app.models import EventRow, UploadRow
from app.response.clock import FakeClock
from app.response.engine import DecisionType, ResponseEngine

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(e)
    for e in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
NOW = datetime(2026, 1, 15, 20, 20, tzinfo=UTC)
T0 = datetime(2026, 11, 17, 9, 0, 0, tzinfo=UTC)
INCIDENTS = score_incidents(
    correlate(EVENTS, load_config(), NOW).incidents,
    EVENTS,
    evaluated_at=NOW,
    config=load_risk_config(assets_path=FIXTURES / "assets.toml"),
)
# Fixture incident A starts at fx-002: High, hosts web-01, db-01 and file-01.
A = next(i for i in INCIDENTS if i.events[0].event_id == "fx-002")


@pytest.fixture(autouse=True)
def _needs_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")


@pytest.fixture
def stored(monkeypatch, tmp_path):
    """The fixture upload with its events and C3's incidents stored. Returns the upload ID."""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE audit_records, response_actions, response_windows, "
                "incident_status_history, incident_lifecycle, incident_events, incidents, "
                "quarantined_records, events, jobs, uploads RESTART IDENTITY CASCADE"
            )
        )
    upload_id = new_id("upl")
    with Session(engine) as session, session.begin():
        session.add(
            UploadRow(
                upload_id=upload_id,
                dataset_id="fixture",
                filename="events.json",
                size_bytes=1,
                sha256="0" * 64,
                received_at=T0,
            )
        )
        session.flush()
        session.execute(EventRow.__table__.insert(), [_event_row(upload_id, e) for e in EVENTS])
    store_incidents(engine, upload_id, INCIDENTS, "test")
    return upload_id


@pytest.fixture
def clock():
    return FakeClock(T0)


@pytest.fixture
def response(clock):
    return ResponseEngine(get_engine(), clock)


@pytest.fixture
def client(stored, response):
    app.dependency_overrides[response_engine] = lambda: response
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def analyst(monkeypatch):
    monkeypatch.setenv("ICD_DEV_USER", "analyst-dev")
    monkeypatch.setenv("ICD_DEV_ROLE", "soc_analyst")


def freeze(response: ResponseEngine, incident: Incident = A) -> None:
    """Take an incident through C5's engine to an open 60 s window (T01, T02, T03)."""
    response.register(incident)
    response.start_analysis(incident.incident_id)
    analysed = Incident.model_validate(
        incident.model_dump()
        | {
            "status": IncidentStatus.UNDER_ANALYSIS,
            "analysis_status": AnalysisStatus.SUCCEEDED,
            "analysis_attempts": 1,
            "latest_report_id": f"rep-{incident.incident_id}",
            "confidence": 0.9,
        }
    )
    outcome = response.record_analysis(analysed, EVENTS)
    assert outcome.froze


def error_code(answer) -> str:
    return answer.json()["error"]["code"]


# ---- incidents -------------------------------------------------------------------------------


def test_list_has_every_stored_incident_newest_first(client):
    items = client.get("/incidents").json()["items"]
    assert len(items) == len(INCIDENTS)
    firsts = [item["incident"]["first_event_at"] for item in items]
    assert firsts == sorted(firsts, reverse=True)
    assert all(item["incident"]["status"] == "new" for item in items)
    assert all(item["recommended_scenario_id"] is None for item in items)


def test_entities_come_from_the_incident_events(client):
    summary = client.get(f"/incidents/{A.incident_id}").json()
    assert {"web-01", "db-01", "file-01"} <= set(summary["entities"]["hosts"])
    assert summary["entities"]["users"] == sorted(summary["entities"]["users"])
    assert summary["incident"]["risk"] == A.risk.model_dump(mode="json")


def test_list_by_upload(client, stored):
    assert len(client.get("/incidents", params={"upload_id": stored}).json()["items"]) == len(
        INCIDENTS
    )
    assert client.get("/incidents", params={"upload_id": "upl-none"}).json() == {"items": []}


def test_unknown_incident_is_404_in_the_error_shape(client):
    for path in ("", "/events", "/report", "/audit", "/decision"):
        answer = client.get(f"/incidents/inc-unknown{path}")
        assert answer.status_code == 404, path
        assert error_code(answer) == "not_found"


def test_events_oldest_first_with_role_and_link_keys(client):
    items = client.get(f"/incidents/{A.incident_id}/events").json()["items"]
    assert [i["event"]["event_id"] for i in items] == sorted(
        (link.event_id for link in A.events),
        key=lambda eid: next(e.timestamp for e in EVENTS if e.event_id == eid),
    )
    roles = {i["event"]["event_id"]: i["role"] for i in items}
    assert roles == {link.event_id: link.role.value for link in A.events}


def test_original_record_reads_the_uploaded_line(client, stored, tmp_path):
    first = A.events[0].event_id
    # The fixture's record_ref is the event ID, so there is no line to read.
    answer = client.get(f"/incidents/{A.incident_id}/events/{first}/original")
    assert answer.status_code == 404
    assert error_code(answer) == "original_not_available"
    assert client.get(f"/incidents/{A.incident_id}/events/fx-999/original").status_code == 404


def test_original_record_for_a_line_reference(client, stored, tmp_path):
    first = A.events[0].event_id
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE events SET data = jsonb_set(data, '{provenance,record_ref}', "
                "'\"events.json:2\"') WHERE event_id = :e"
            ),
            {"e": first},
        )
    (tmp_path / stored).write_text("line one\nline two\n", encoding="utf-8")
    body = client.get(f"/incidents/{A.incident_id}/events/{first}/original").json()
    assert body == {
        "event_id": first,
        "record_ref": "events.json:2",
        "source_file": "events.json",
        "line": "line two",
    }


def test_report_is_not_stored_yet(client):
    answer = client.get(f"/incidents/{A.incident_id}/report")
    assert answer.status_code == 404
    assert error_code(answer) == "report_not_available"


# ---- window, decisions, audit ------------------------------------------------------------------


def test_window_after_a_freeze(client, response):
    assert client.get(f"/response-windows/{A.incident_id}").status_code == 404
    freeze(response)
    window = client.get(f"/response-windows/{A.incident_id}").json()
    assert window["status"] == "open"
    assert window["deadline_at"] == "2026-11-17T09:01:00.000Z"
    assert window["server_time"] == "2026-11-17T09:00:00.000Z"
    summary = client.get(f"/incidents/{A.incident_id}").json()
    assert summary["incident"]["status"] == "awaiting_human_decision"
    assert summary["recommended_scenario_id"] == window["recommended_scenario_id"]


def test_decision_needs_an_identity(client, response, monkeypatch):
    monkeypatch.delenv("ICD_DEV_USER", raising=False)
    freeze(response)
    answer = client.post(f"/incidents/{A.incident_id}/decisions", json={"decision": "reject"})
    assert answer.status_code == 403
    assert error_code(answer) == "not_authorized"


def test_approve_records_the_decision_and_the_simulated_action(client, response, analyst):
    freeze(response)
    window = client.get(f"/response-windows/{A.incident_id}").json()
    answer = client.post(
        f"/incidents/{A.incident_id}/decisions",
        json={"decision": "approve", "window_id": window["window_id"], "comment": "ok"},
    )
    assert answer.status_code == 201, answer.text
    record = answer.json()
    assert record["decision"] == "approve"
    assert record["decided_by"] == "analyst-dev"
    assert record["scenario_id"] == window["recommended_scenario_id"]
    assert record["window_id"] == window["window_id"]
    assert record["action"]["simulated"] is True
    assert record["action"]["state"] in ("simulated_succeeded", "simulated_failed")
    assert client.get(f"/incidents/{A.incident_id}/decision").json() == record
    assert client.get(f"/response-windows/{A.incident_id}").json()["status"] == "decided"

    again = client.post(f"/incidents/{A.incident_id}/decisions", json={"decision": "reject"})
    assert again.status_code == 409
    assert error_code(again) == "already_decided"

    types = [
        r["event_type"] for r in client.get(f"/incidents/{A.incident_id}/audit").json()["items"]
    ]
    assert "decision.recorded" in types
    assert "action.simulated" in types


def test_reject_keeps_the_incident_awaiting_and_releases_isolation(client, response, analyst):
    freeze(response)
    record = client.post(
        f"/incidents/{A.incident_id}/decisions", json={"decision": "reject"}
    ).json()
    assert record["action"] is None
    assert record["incident_status"] == "awaiting_human_decision"
    trail = response.audit_trail(A.incident_id)
    assert AuditEventType.ISOLATION_RELEASED in [r.event_type for r in trail]


def test_decision_after_the_deadline_is_window_expired(client, response, clock, analyst):
    freeze(response)
    window_id = response.window_of(A.incident_id).window_id
    clock.advance(60)
    answer = client.post(
        f"/incidents/{A.incident_id}/decisions",
        json={"decision": "reject", "window_id": window_id},
    )
    assert answer.status_code == 409
    assert error_code(answer) == "window_expired"


def test_decision_on_an_incident_not_awaiting(client, analyst):
    answer = client.post(f"/incidents/{A.incident_id}/decisions", json={"decision": "reject"})
    assert answer.status_code == 404  # not tracked by C5's engine yet
    response = ResponseEngine(get_engine(), FakeClock(T0))
    response.register(A)
    answer = client.post(f"/incidents/{A.incident_id}/decisions", json={"decision": "reject"})
    assert answer.status_code == 409
    assert error_code(answer) == "not_awaiting_decision"


def test_bad_decision_bodies_are_422(client, response, analyst):
    freeze(response)
    for body in (
        {"decision": "maybe"},
        {"decision": "select"},
        {"decision": "select", "scenario_id": "S9"},
        {"decision": "reject", "scenario_id": "S1"},
    ):
        answer = client.post(f"/incidents/{A.incident_id}/decisions", json=body)
        assert answer.status_code == 422, body
        assert error_code(answer) == "validation_error"


# ---- notifications (S8-D8) ---------------------------------------------------------------------


def test_notifications_are_c5s_notification_records(client, response):
    assert client.get("/notifications").json() == {"items": []}
    freeze(response)
    items = client.get("/notifications").json()["items"]
    assert len(items) == 1
    sent = items[0]
    assert sent["event_type"] == "notification.sent"
    assert sent["incident_id"] == A.incident_id
    assert sent["details"] == {"reason": "freeze_started", "recipients": "soc_analyst,soc_manager"}
    trail = client.get(f"/incidents/{A.incident_id}/audit").json()["items"]
    assert sent in trail


def test_notifications_after_a_record_and_limit(client, response):
    freeze(response)
    seen = client.get("/notifications").json()["items"][0]["record_id"]
    assert client.get("/notifications", params={"after": seen}).json() == {"items": []}
    # An unknown marker, for example from before a database reset, is ignored.
    assert len(client.get("/notifications", params={"after": "aud-gone"}).json()["items"]) == 1
    assert client.get("/notifications", params={"limit": 0}).status_code == 422
    assert client.get("/notifications", params={"limit": 101}).status_code == 422


# ---- WebSocket -------------------------------------------------------------------------------


def test_socket_sends_opened_then_decided(client, response):
    freeze(response)
    with client.websocket_connect(f"/ws/response-windows?incident_id={A.incident_id}") as ws:
        opened = ws.receive_json()
        assert opened["type"] == "response_window.opened"
        assert opened["deadline_at"] == "2026-11-17T09:01:00.000Z"
        response.decide(A.incident_id, DecisionType.REJECT, actor="analyst-dev", role="soc_analyst")
        decided = ws.receive_json()
        assert decided == {
            "type": "response_window.decided",
            "incident_id": A.incident_id,
            "window_id": opened["window_id"],
            "server_time": decided["server_time"],
        }


def test_socket_sends_opened_when_a_window_opens_later(client, response):
    with client.websocket_connect(f"/ws/response-windows?incident_id={A.incident_id}") as ws:
        freeze(response)
        assert ws.receive_json()["type"] == "response_window.opened"


def test_window_events_between_two_reads(stored, response, clock):
    response_engine_ = response
    freeze(response_engine_)
    opened = response_engine_.window_of(A.incident_id)
    assert _window_events(None, None) == []
    assert [e["type"] for e in _window_events(None, opened)] == ["response_window.opened"]
    assert _window_events(opened, opened) == []
    clock.advance(61)
    response_engine_.expire_due()
    expired = response_engine_.window_of(A.incident_id)
    assert [e["type"] for e in _window_events(opened, expired)] == ["response_window.expired"]
