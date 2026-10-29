"""Response engine on PostgreSQL with a fake clock (Week 2 gate: fake-clock tests for all paths).

Paths: analyst decides early, deadline expires, decision at the deadline, failed report, low
confidence, reject, no match, simulated failure, double and concurrent expiry, worker restart,
authorization, and the append-only audit trail. Every action must be simulated and audited.
"""

import os
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.contracts import (
    ActionState,
    ActionTrigger,
    AuditEventType,
    AuditResult,
    IncidentStatus,
    ScenarioId,
    UserRole,
)
from app.db import get_engine
from app.response import NoFreezeReason, TransitionRefused
from app.response.clock import DatabaseClock, FakeClock
from app.response.engine import (
    DecisionRefused,
    DecisionType,
    ExpiryResult,
    RefusalReason,
    ResponseEngine,
)
from app.response.expiry import run_expiry_loop

E = AuditEventType
S = IncidentStatus
T0 = datetime(2026, 11, 2, 9, 15, 30, 250000, tzinfo=UTC)
ANALYST = dict(actor="usr-analyst-1", role=UserRole.SOC_ANALYST)


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
                "incident_status_history, incident_lifecycle RESTART IDENTITY CASCADE"
            )
        )
    return engine


@pytest.fixture
def clock():
    return FakeClock(T0)


@pytest.fixture
def response(db, clock, config):
    return ResponseEngine(db, clock, config)


@pytest.fixture
def frozen(response, incident_a, events, analysed):
    """Incident A registered, analysed with confidence 0.9 and frozen at T0."""
    response.register(incident_a)
    response.start_analysis(incident_a.incident_id)
    outcome = response.record_analysis(analysed(incident_a, 0.9), events)
    assert outcome.froze
    return incident_a.incident_id


def types(response, incident_id):
    return [r.event_type for r in response.audit_trail(incident_id)]


def assert_every_action_simulated_and_audited(response, incident_id):
    trail = response.audit_trail(incident_id)
    for record in trail:
        assert record.simulated == (record.event_type in (E.ACTION_SIMULATED, E.ISOLATION_RELEASED))
        if record.simulated:
            assert record.details["label"] == "SIMULATED"
    audited = {r.details.get("action_id") for r in trail if r.event_type == E.ACTION_SIMULATED}
    for action in response.actions_of(incident_id):
        assert action.simulated is True and action.parameters["label"] == "SIMULATED"
        assert action.action_id in audited


# ---- freeze and the server-held deadline ---------------------------------------------------


def test_freeze_stores_the_deadline_in_the_database(response, frozen, clock):
    window = response.window_of(frozen)
    assert window.status == "open"
    assert window.started_at == T0
    assert window.deadline_at == T0 + timedelta(seconds=60)
    assert window.recommended_scenario_id == "S2"
    assert response.status_of(frozen) == S.AWAITING_HUMAN_DECISION
    assert response.isolated(frozen) is True
    clock.advance(12.5)
    assert window.as_json() | {"server_time": None} == {
        "incident_id": frozen,
        "window_id": window.window_id,
        "status": "open",
        "started_at": "2026-11-02T09:15:30.250Z",
        "deadline_at": "2026-11-02T09:16:30.250Z",
        "server_time": None,
        "recommended_scenario_id": "S2",
    }
    assert response.window_of(frozen).server_time == T0 + timedelta(seconds=12.5)
    assert types(response, frozen) == [
        E.STATUS_CHANGED,  # T01
        E.STATUS_CHANGED,  # T02
        E.STATUS_CHANGED,  # T03
        E.ACTION_SIMULATED,  # isolation, simulated
        E.RESPONSE_WINDOW_OPENED,
        E.NOTIFICATION_SENT,
    ]


def test_refresh_never_creates_or_extends_a_window(response, frozen, clock):
    first = response.window_of(frozen)
    clock.advance(30)
    again = response.window_of(frozen)
    assert (again.window_id, again.deadline_at) == (first.window_id, first.deadline_at)


# ---- the three analyst options and T16 ----------------------------------------------------


def test_analyst_decides_early_and_expiry_selects_nothing(response, frozen, clock):
    clock.advance(10)
    outcome = response.decide(frozen, DecisionType.APPROVE, scenario_id=ScenarioId.S2, **ANALYST)
    assert outcome.status == S.RESOLVED
    action = outcome.action
    assert action.state == ActionState.SIMULATED_SUCCEEDED
    assert (action.trigger, action.decided_by) == (ActionTrigger.ANALYST_DECISION, "usr-analyst-1")
    assert action.target.ip == "203.0.113.10" and action.target.host == "web-01"
    assert response.window_of(frozen).status == "decided"

    clock.advance(60)
    assert response.expire_due() == []
    duplicate = response.expire_window(response.window_of(frozen).window_id)
    assert duplicate.result == ExpiryResult.DUPLICATE_IGNORED
    assert len(response.actions_of(frozen)) == 1
    assert types(response, frozen)[-1] == E.EXPIRY_DUPLICATE_IGNORED
    assert_every_action_simulated_and_audited(response, frozen)


def test_select_another_scenario(response, frozen, clock):
    clock.advance(5)
    outcome = response.decide(frozen, DecisionType.SELECT, scenario_id=ScenarioId.S3, **ANALYST)
    assert outcome.status == S.RESOLVED
    assert outcome.action.scenario_id == ScenarioId.S3
    assert outcome.action.target.account == "svc-db"


def test_reject_releases_the_isolation_and_keeps_the_incident_open(response, frozen, clock):
    clock.advance(20)
    outcome = response.decide(frozen, DecisionType.REJECT, **ANALYST)
    assert outcome.status == S.AWAITING_HUMAN_DECISION and outcome.action is None
    assert response.isolated(frozen) is False
    assert response.window_of(frozen).status == "decided"
    assert E.ISOLATION_RELEASED in types(response, frozen)
    clock.advance(60)
    assert response.expire_due() == []
    # Still open: T16 with a comment resolves it without any action.
    with pytest.raises(DecisionRefused) as refused:
        response.decide(frozen, DecisionType.NO_ACTION, **ANALYST)
    assert refused.value.reason == RefusalReason.COMMENT_REQUIRED
    done = response.decide(frozen, DecisionType.NO_ACTION, comment="false positive", **ANALYST)
    assert done.status == S.RESOLVED
    assert response.actions_of(frozen) == []


def test_no_action_is_refused_while_the_window_is_open(response, frozen):
    with pytest.raises(DecisionRefused) as refused:
        response.decide(frozen, DecisionType.NO_ACTION, comment="looks fine", **ANALYST)
    assert refused.value.reason == RefusalReason.WINDOW_OPEN


def test_approve_must_be_the_recommended_scenario(response, frozen):
    with pytest.raises(DecisionRefused) as refused:
        response.decide(frozen, DecisionType.APPROVE, scenario_id=ScenarioId.S1, **ANALYST)
    assert refused.value.reason == RefusalReason.SCENARIO_MISMATCH


# ---- expiry ------------------------------------------------------------------------------


def test_deadline_expires_and_the_system_selects_exactly_once(response, frozen, clock):
    clock.advance(59.999)
    assert response.expire_due() == []
    clock.advance(0.001)
    [outcome] = response.expire_due()
    assert outcome.result == ExpiryResult.SELECTED and outcome.status == S.RESOLVED
    action = outcome.action
    assert (action.scenario_id, action.trigger, action.decided_by) == (
        ScenarioId.S2,
        ActionTrigger.WINDOW_EXPIRY,
        "system",
    )
    assert response.expire_due() == []  # a second pass finds nothing
    again = response.expire_window(outcome.window_id)  # a duplicate event is ignored
    assert again.result == ExpiryResult.DUPLICATE_IGNORED
    assert len(response.actions_of(frozen)) == 1

    trail = response.audit_trail(frozen)
    expired = next(r for r in trail if r.event_type == E.RESPONSE_WINDOW_EXPIRED)
    assert expired.actor == "system" and "expired" in expired.details["statement"]
    selected = next(r for r in trail if r.event_type == E.SCENARIO_SELECTED)
    assert selected.details["incident_type"] == "Backdoors"
    assert selected.details["confidence_band"] == "high"
    assert_every_action_simulated_and_audited(response, frozen)


def test_decision_at_the_deadline_is_refused_and_expiry_wins(response, frozen, clock):
    clock.advance(60)
    with pytest.raises(DecisionRefused) as refused:
        response.decide(frozen, DecisionType.APPROVE, **ANALYST)
    assert (refused.value.reason, refused.value.http_status) == (RefusalReason.WINDOW_EXPIRED, 409)
    assert response.status_of(frozen) == S.AWAITING_HUMAN_DECISION
    refusal = response.audit_trail(frozen)[-1]
    assert (refusal.event_type, refusal.result) == (E.DECISION_REFUSED, AuditResult.REFUSED)
    [outcome] = response.expire_due()
    assert outcome.result == ExpiryResult.SELECTED


def test_decision_one_millisecond_before_the_deadline_wins(response, frozen, clock):
    clock.advance(59.999)
    outcome = response.decide(frozen, DecisionType.APPROVE, **ANALYST)
    assert outcome.status == S.RESOLVED
    clock.advance(1)
    assert response.expire_due() == []


def test_worker_restart_processes_an_overdue_window_once(response, frozen, clock):
    clock.advance(300)  # the worker was down for five minutes
    [outcome] = response.expire_due()
    assert outcome.result == ExpiryResult.SELECTED
    expired = next(
        r for r in response.audit_trail(frozen) if r.event_type == E.RESPONSE_WINDOW_EXPIRED
    )
    assert expired.details["deadline_at"] == "2026-11-02T09:16:30.250Z"
    assert expired.details["late_ms"] == 240_000


def test_two_workers_expiring_the_same_window_select_once(db, frozen, clock, config):
    clock.advance(61)
    window_id = ResponseEngine(db, clock, config).window_of(frozen).window_id
    results, barrier = [], threading.Barrier(2)

    def worker():
        barrier.wait()
        results.append(ResponseEngine(db, clock, config).expire_window(window_id).result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [ExpiryResult.DUPLICATE_IGNORED, ExpiryResult.SELECTED]
    assert len(ResponseEngine(db, clock, config).actions_of(frozen)) == 1


def test_no_catalogue_match_escalates_and_runs_nothing(
    db, clock, config, incident_a, events, analysed
):
    response = ResponseEngine(db, clock, replace(config, selection_order=()))
    response.register(incident_a)
    response.start_analysis(incident_a.incident_id)
    response.record_analysis(analysed(incident_a, 0.9), events)
    clock.advance(60)
    [outcome] = response.expire_due()
    assert (outcome.result, outcome.status) == (ExpiryResult.NO_MATCH, S.ESCALATED)
    assert response.actions_of(incident_a.incident_id) == []
    trail = types(response, incident_a.incident_id)
    assert trail[-2:] == [E.SCENARIO_NO_MATCH, E.NOTIFICATION_SENT]


def test_simulated_failure_escalates_then_an_analyst_recovers(
    db, clock, config, incident_a, events, analysed
):
    failures = iter(["simulated executor failure"])
    response = ResponseEngine(db, clock, config, failure_rule=lambda _: next(failures, None))
    response.register(incident_a)
    response.start_analysis(incident_a.incident_id)
    response.record_analysis(analysed(incident_a, 0.9), events)
    clock.advance(60)
    [outcome] = response.expire_due()
    assert outcome.status == S.ESCALATED
    assert outcome.action.state == ActionState.SIMULATED_FAILED
    failed = [
        r
        for r in response.audit_trail(incident_a.incident_id)
        if r.event_type == E.ACTION_SIMULATED
    ][-1]
    assert failed.result == AuditResult.FAILURE
    assert failed.details["failure_reason"] == "simulated executor failure"

    clock.advance(5)  # T12: the analyst picks a scenario from Escalated
    recovered = response.decide(
        incident_a.incident_id, DecisionType.SELECT, scenario_id=ScenarioId.S1, **ANALYST
    )
    assert recovered.status == S.RESOLVED
    assert_every_action_simulated_and_audited(response, incident_a.incident_id)


# ---- paths that must never freeze ----------------------------------------------------------


def test_failed_report_never_freezes(response, incident_a, events, analysed):
    response.register(incident_a)
    response.start_analysis(incident_a.incident_id)
    outcome = response.record_analysis(analysed(incident_a, None), events)
    assert not outcome.froze and outcome.window is None
    assert response.status_of(incident_a.incident_id) == S.UNDER_ANALYSIS
    assert response.window_of(incident_a.incident_id) is None
    assert types(response, incident_a.incident_id)[-1] == E.ANALYSIS_FAILED


def test_low_confidence_waits_for_a_human_with_no_timer(response, incident_a, events, analysed):
    response.register(incident_a)
    response.start_analysis(incident_a.incident_id)
    outcome = response.record_analysis(analysed(incident_a, 0.6), events)
    assert outcome.reasons == (NoFreezeReason.CONFIDENCE_BELOW_THRESHOLD,)
    assert outcome.status == S.AWAITING_HUMAN_DECISION
    assert response.window_of(incident_a.incident_id) is None
    assert response.isolated(incident_a.incident_id) is False
    # FR-25: the recommendation exists, so the analyst may approve it without a window.
    approved = response.decide(incident_a.incident_id, DecisionType.APPROVE, **ANALYST)
    assert approved.status == S.RESOLVED and approved.action.window_id is None
    assert approved.action.parameters["isolation"] == "applied"


def test_medium_incident_without_a_host_cannot_be_approved(
    response, fixture_incident, events, analysed
):
    incident = fixture_incident("fx-005")  # F: Medium, no entities at all
    response.register(incident)
    response.start_analysis(incident.incident_id)
    outcome = response.record_analysis(analysed(incident, 1.0), events)
    assert not outcome.froze and outcome.recommended_scenario_id is None
    with pytest.raises(DecisionRefused) as refused:
        response.decide(incident.incident_id, DecisionType.APPROVE, **ANALYST)
    assert refused.value.reason == RefusalReason.NO_RECOMMENDATION
    with pytest.raises(DecisionRefused) as refused:
        response.decide(
            incident.incident_id, DecisionType.SELECT, scenario_id=ScenarioId.S1, **ANALYST
        )
    assert (refused.value.reason, refused.value.http_status) == (
        RefusalReason.REQUIRED_DATA_MISSING,
        422,
    )


# ---- authorization, refused transitions, append-only audit ---------------------------------


@pytest.mark.parametrize(
    "role", [UserRole.SOC_MANAGER, UserRole.SECURITY_ENGINEER, UserRole.SYSTEM_ADMINISTRATOR]
)
def test_only_a_soc_analyst_may_decide(response, frozen, role):
    with pytest.raises(DecisionRefused) as refused:
        response.decide(frozen, DecisionType.APPROVE, actor="usr-x", role=role)
    assert refused.value.http_status == 403
    record = response.audit_trail(frozen)[-1]
    assert (record.event_type, record.actor_role) == (E.DECISION_REFUSED, role)
    assert response.window_of(frozen).status == "open"


def test_undefined_transition_is_refused_and_audited(response, incident_a):
    response.register(incident_a)
    with pytest.raises(TransitionRefused):
        response.register(incident_a)
    response.start_analysis(incident_a.incident_id)
    with pytest.raises(TransitionRefused):
        response.start_analysis(incident_a.incident_id)
    refused = response.audit_trail(incident_a.incident_id)[-1]
    assert refused.event_type == E.TRANSITION_REFUSED
    assert refused.details == {
        "transition_id": "T15",
        "from_status": "under_analysis",
        "trigger": "analysis_started",
    }
    assert response.status_of(incident_a.incident_id) == S.UNDER_ANALYSIS


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_records SET actor = 'x'", "DELETE FROM audit_records"]
)
def test_audit_records_are_append_only(db, frozen, statement):
    with pytest.raises(DBAPIError, match="append-only"), db.begin() as connection:
        connection.execute(text(statement))


def test_status_history_has_every_change(db, frozen):
    with db.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT transition_id, previous_status, new_status FROM incident_status_history "
                "WHERE incident_id = :id ORDER BY seq"
            ),
            {"id": frozen},
        ).all()
    assert [tuple(r) for r in rows] == [
        ("T01", None, "new"),
        ("T02", "new", "under_analysis"),
        ("T03", "under_analysis", "awaiting_human_decision"),
    ]


# ---- clock and the expiry loop -------------------------------------------------------------


def test_database_clock_is_timezone_aware_and_moves(db):
    clock = DatabaseClock(db)
    first, second = clock.now(), clock.now()
    assert first.tzinfo is not None and second >= first


def test_expiry_loop_expires_due_windows(db, frozen, clock, config):
    clock.advance(61)
    stop = threading.Event()
    thread = threading.Thread(target=run_expiry_loop, args=(db, stop, clock, 0.01))
    thread.start()
    engine = ResponseEngine(db, clock, config)
    for _ in range(500):
        if engine.status_of(frozen) == S.RESOLVED:
            break
        threading.Event().wait(0.01)
    stop.set()
    thread.join(timeout=5)
    assert engine.status_of(frozen) == S.RESOLVED
    assert len(engine.actions_of(frozen)) == 1


def test_an_approved_action_left_unrun_is_simulated_once_after_a_restart(response, frozen, db):
    # Simulate a crash between the decision's commit and the simulation: put the action back.
    outcome = response.decide(frozen, DecisionType.APPROVE, **ANALYST)
    action = outcome.action
    with db.begin() as connection:
        connection.execute(
            text(
                "UPDATE response_actions SET state = 'approved', data = data || "
                "jsonb_build_object('state', 'approved', 'executed_at', null) "
                "WHERE action_id = :id"
            ),
            {"id": action.action_id},
        )
        connection.execute(
            text(
                "UPDATE incident_lifecycle SET status = 'response_in_progress' "
                "WHERE incident_id = :id"
            ),
            {"id": frozen},
        )
    assert response.run_pending_actions() == [action.action_id]
    assert response.run_pending_actions() == []
    assert response.status_of(frozen) == S.RESOLVED
