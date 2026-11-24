"""Demo paths A and B end to end on PostgreSQL (tracker task 30, docs/demo-script.md).

Unlike test_engine_db.py, the incident here is not built by hand: it goes through the real
pipeline pieces in the order C1's analysis job calls them (C1/C5 agreement, 24 Nov):

    stored events -> C3 correlation + risk -> stored incident -> register (T01)
    -> start_analysis (T02) -> AI1 analyze_incident (stub model) -> record_analysis
    -> freeze (T03) -> path A: analyst approves | path B: nobody decides, expiry selects

Needs Postgres (DATABASE_URL). The stub model stands in for the HPC model, as in the demo's
HPC fallback.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analysis.store import analyze_incident
from app.analysis.stub import StubGenerator
from app.contracts import (
    ActionState,
    ActionTrigger,
    AuditEventType,
    Event,
    IncidentStatus,
    ScenarioId,
    UserRole,
)
from app.correlation import correlate, load_config, score_incidents
from app.db import get_engine
from app.evidence.store import load_incident_events
from app.incidents.store import store_incidents
from app.jobs.ingest import _event_row
from app.jobs.queue import new_id
from app.models import EventRow, UploadRow
from app.response.clock import FakeClock
from app.response.engine import DecisionType, ExpiryResult, ResponseEngine

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(item)
    for item in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
NOW = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
ANALYST = dict(actor="usr-analyst-1", role=UserRole.SOC_ANALYST)
E = AuditEventType
S = IncidentStatus


@pytest.fixture(autouse=True)
def _needs_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")


@pytest.fixture
def db():
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE audit_records, response_actions, response_windows, "
                "incident_status_history, incident_lifecycle, analysis_reports, masking_maps, "
                "incident_events, incidents, quarantined_records, events, jobs, uploads "
                "RESTART IDENTITY CASCADE"
            )
        )
    return engine


def _store_upload(engine) -> list[str]:
    """Upload the fixture events, correlate and score them as C1's correlating stage does."""
    upload_id = new_id("upl")
    with Session(engine) as session, session.begin():
        session.add(UploadRow(upload_id=upload_id, dataset_id="fixture", filename="events.json",
                              size_bytes=1, sha256="0" * 64, received_at=NOW))  # fmt: skip
        session.flush()
        session.execute(EventRow.__table__.insert(), [_event_row(upload_id, e) for e in EVENTS])
    result = correlate(EVENTS, load_config(), NOW, scope=upload_id)
    incidents = list(score_incidents(result.incidents, EVENTS, NOW))
    store_incidents(engine, upload_id, incidents, result.config_version)
    return [i.incident_id for i in incidents]


def _pipeline(engine, response: ResponseEngine, incident_id: str):
    """The analysis job's engine calls, in C1's order, on one stored incident."""
    incident, _ = load_incident_events(engine, incident_id)
    if response.status_of(incident_id) is None:
        response.register(incident)
    if response.status_of(incident_id) == S.NEW:
        response.start_analysis(incident_id)
    analyze_incident(engine, incident_id, StubGenerator(), lambda: NOW)
    analysed, events = load_incident_events(engine, incident_id)
    return response.record_analysis(analysed, events)


@pytest.fixture
def clock():
    return FakeClock(NOW)


@pytest.fixture
def frozen(db, clock):
    """Every stored incident goes through the pipeline; the demo uses the one that froze."""
    response = ResponseEngine(db, clock)
    outcomes = {iid: _pipeline(db, response, iid) for iid in _store_upload(db)}
    froze = [iid for iid, outcome in outcomes.items() if outcome.froze]
    assert froze, {iid: o.reasons for iid, o in outcomes.items()}
    # Only High incidents with a valid, confident report may freeze (FR-43, OD-16).
    for iid, outcome in outcomes.items():
        if iid not in froze:
            assert outcome.reasons, iid
            assert response.window_of(iid) is None
    return response, froze[0]


def test_stored_incident_reaches_the_freeze_through_the_real_pipeline(frozen, clock):
    response, incident_id = frozen
    window = response.window_of(incident_id)
    assert window.status == "open"
    assert window.deadline_at == NOW + timedelta(seconds=60)
    assert window.recommended_scenario_id == "S2"
    assert response.status_of(incident_id) == S.AWAITING_HUMAN_DECISION
    assert response.isolated(incident_id) is True
    assert [r.event_type for r in response.audit_trail(incident_id)][:2] == [
        E.STATUS_CHANGED,  # T01 New
        E.STATUS_CHANGED,  # T02 Under Analysis
    ]


def test_demo_path_a_analyst_approves_before_the_deadline(frozen, clock):
    response, incident_id = frozen
    clock.advance(20)
    outcome = response.decide(
        incident_id, DecisionType.APPROVE, scenario_id=ScenarioId.S2, **ANALYST
    )
    assert outcome.status == S.RESOLVED
    assert outcome.action.trigger == ActionTrigger.ANALYST_DECISION
    assert outcome.action.state == ActionState.SIMULATED_SUCCEEDED
    assert outcome.action.simulated is True
    clock.advance(60)
    assert response.expire_due() == []  # the deadline passing later changes nothing
    assert len(response.actions_of(incident_id)) == 1


def test_demo_path_b_nobody_decides_and_the_system_selects_at_expiry(frozen, clock):
    response, incident_id = frozen
    clock.advance(59.999)
    assert response.expire_due() == []
    clock.advance(0.001)
    [outcome] = response.expire_due()
    assert outcome.result == ExpiryResult.SELECTED
    assert outcome.status == S.RESOLVED
    action = outcome.action
    assert (action.scenario_id, action.trigger, action.decided_by) == (
        ScenarioId.S2,
        ActionTrigger.WINDOW_EXPIRY,
        "system",
    )
    assert action.simulated is True and action.parameters["label"] == "SIMULATED"
    trail = [r.event_type for r in response.audit_trail(incident_id)]
    assert E.RESPONSE_WINDOW_EXPIRED in trail and E.SCENARIO_SELECTED in trail
    assert E.ACTION_SIMULATED in trail
