"""Timed simulated containment on PostgreSQL with a fake clock (P2 of the competitor feature
study, PR #51, F-B: a stateful response that reverts itself after a timeout, re-implemented).

A succeeded S2 blocks the source IP (simulated) for 60 minutes; a repeat offender's next block
lasts 120, then 240 minutes (decision D5). The revert is simulated and audited once. Nothing else
changes: the isolation, the incident status, the window and the existing audit records.
"""

import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.contracts import ActionState, AuditEventType, IncidentStatus, ScenarioId, UserRole
from app.db import get_engine
from app.response.clock import FakeClock
from app.response.containment import ContainmentConfig
from app.response.engine import DecisionType, ResponseEngine
from app.response.expiry import run_expiry_loop

E = AuditEventType
S = IncidentStatus
T0 = datetime(2026, 11, 2, 9, 15, 30, 250000, tzinfo=UTC)
ANALYST = dict(actor="usr-analyst-1", role=UserRole.SOC_ANALYST)
IP = "203.0.113.10"  # fixture incident A's external source
D5 = ContainmentConfig("containment-test", (60, 120, 240))


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
                "TRUNCATE simulated_containments, audit_records, response_actions, "
                "response_windows, incident_status_history, incident_lifecycle "
                "RESTART IDENTITY CASCADE"
            )
        )
    return engine


@pytest.fixture
def clock():
    return FakeClock(T0)


@pytest.fixture
def response(db, clock, config):
    return ResponseEngine(db, clock, config, containment=D5)


@pytest.fixture
def freeze(response, incident_a, events, analysed):
    """freeze(n) -> the ID of copy n of incident A (same events and source IP), frozen now."""

    def run(n: int = 0, engine: ResponseEngine | None = None) -> str:
        engine = engine or response
        incident = incident_a.model_copy(update={"incident_id": f"inc-a-copy-{n}"})
        engine.register(incident)
        engine.start_analysis(incident.incident_id)
        assert engine.record_analysis(analysed(incident, 0.9), events).froze
        return incident.incident_id

    return run


def block(response, freeze, n: int = 0, scenario=ScenarioId.S2) -> str:
    incident_id = freeze(n)
    # S2 is the recommendation for incident A; any other scenario is a select (spec section 8).
    decision = DecisionType.APPROVE if scenario == ScenarioId.S2 else DecisionType.SELECT
    outcome = response.decide(incident_id, decision, scenario_id=scenario, **ANALYST)
    assert outcome.action.state == ActionState.SIMULATED_SUCCEEDED
    return incident_id


def reverts(response, incident_id):
    return [
        r
        for r in response.audit_trail(incident_id)
        if r.event_type == E.ACTION_SIMULATED and r.details.get("trigger") == "containment_expiry"
    ]


# ---- start --------------------------------------------------------------------------------


def test_a_simulated_ip_block_records_its_planned_end(response, freeze, clock):
    clock.advance(10)
    incident_id = block(response, freeze)
    [held] = response.containments_of(incident_id)
    assert (held.kind, held.target, held.status, held.offence) == ("block_ip", IP, "active", 1)
    assert held.started_at == T0 + timedelta(seconds=10)
    assert held.ends_at == held.started_at + timedelta(minutes=60)
    assert held.incident_id == incident_id
    assert held.action_id == response.actions_of(incident_id)[-1].action_id
    assert held.config_version == "containment-test"
    assert held.simulated is True


def test_starting_a_block_adds_no_audit_record(response, freeze, db, clock, config):
    # The same path without containment writes exactly the same audit records.
    with_block = block(response, freeze, 0)
    plain = ResponseEngine(db, clock, config, containment=ContainmentConfig("off", ()))
    without = freeze(1, plain)
    plain.decide(without, DecisionType.APPROVE, scenario_id=ScenarioId.S2, **ANALYST)
    assert [r.event_type for r in response.audit_trail(with_block)] == [
        r.event_type for r in plain.audit_trail(without)
    ]
    assert plain.containments_of(without) == []


@pytest.mark.parametrize("scenario", [ScenarioId.S1, ScenarioId.S3])
def test_only_the_ip_block_of_s2_ends_on_its_own(response, freeze, scenario):
    incident_id = block(response, freeze, scenario=scenario)
    assert response.containments_of(incident_id) == []


def test_a_failed_simulation_blocks_nothing(db, clock, config, freeze):
    failing = ResponseEngine(
        db, clock, config, containment=D5, failure_rule=lambda _: "simulated failure"
    )
    incident_id = freeze(0, failing)
    outcome = failing.decide(incident_id, DecisionType.APPROVE, **ANALYST)
    assert outcome.action.state == ActionState.SIMULATED_FAILED
    assert failing.containments_of(incident_id) == []


def test_the_system_selection_at_the_deadline_blocks_too(response, freeze, clock):
    incident_id = freeze()
    clock.advance(60)
    [outcome] = response.expire_due()
    assert outcome.action.scenario_id == ScenarioId.S2
    [held] = response.containments_of(incident_id)
    assert held.ends_at == T0 + timedelta(seconds=60, minutes=60)


# ---- revert -------------------------------------------------------------------------------


def test_revert_at_the_planned_end_and_not_before(response, freeze, clock):
    incident_id = block(response, freeze)
    clock.advance(60 * 60 - 0.001)
    assert response.revert_due() == []
    assert reverts(response, incident_id) == []
    clock.advance(0.001)  # exactly at ends_at: due (boundary inclusive, like the windows)
    [reverted] = response.revert_due()
    [held] = response.containments_of(incident_id)
    assert held.containment_id == reverted
    assert (held.status, held.reverted_at) == ("reverted", T0 + timedelta(minutes=60))

    [record] = reverts(response, incident_id)
    assert record.simulated is True
    assert record.actor == "system" and record.actor_role is None
    assert record.details["label"] == "SIMULATED"
    assert record.details["reverts"] == "block_ip"
    assert record.details["ip"] == IP
    assert record.details["containment_id"] == held.containment_id
    assert record.details["reverted_action_id"] == held.action_id
    assert record.details["offence"] == 1


def test_revert_changes_nothing_else(response, freeze, clock):
    incident_id = block(response, freeze)
    before = (response.status_of(incident_id), response.isolated(incident_id))
    actions = response.actions_of(incident_id)
    clock.advance(60 * 60)
    response.revert_due()
    # The host stays isolated: only an analyst ends isolation (S4, spec section 9).
    assert (response.status_of(incident_id), response.isolated(incident_id)) == before
    assert response.actions_of(incident_id) == actions
    assert response.window_of(incident_id).status == "decided"


def test_a_second_pass_or_a_restart_reverts_nothing_again(response, freeze, db, clock, config):
    incident_id = block(response, freeze)
    clock.advance(3 * 60 * 60)  # the worker was down for three hours
    assert len(response.revert_due()) == 1
    assert ResponseEngine(db, clock, config, containment=D5).revert_due() == []
    assert len(reverts(response, incident_id)) == 1


def test_two_workers_revert_the_same_block_once(response, freeze, db, clock, config):
    incident_id = block(response, freeze)
    clock.advance(60 * 60)
    results, barrier = [], threading.Barrier(2)

    def worker():
        engine = ResponseEngine(db, clock, config, containment=D5)
        barrier.wait()
        results.extend(engine.revert_due())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 1
    assert len(reverts(response, incident_id)) == 1


def test_the_expiry_loop_reverts_due_blocks(response, freeze, db, clock, config):
    incident_id = block(response, freeze)
    clock.advance(60 * 60)
    stop = threading.Event()
    loop = threading.Thread(
        target=run_expiry_loop, args=(db, stop, clock, 0.01), kwargs={"containment": D5}
    )
    loop.start()
    for _ in range(500):
        if reverts(response, incident_id):
            break
        threading.Event().wait(0.01)
    stop.set()
    loop.join(timeout=5)
    assert len(reverts(response, incident_id)) == 1


# ---- the same IP again --------------------------------------------------------------------


def test_the_same_ip_while_blocked_extends_the_block_and_never_shortens_it(response, freeze, clock):
    first = block(response, freeze, 0)
    clock.advance(30 * 60)
    second = block(response, freeze, 1)
    [held] = response.containments_of(first)
    assert response.containments_of(second) == [held]
    assert held.offence == 1 and held.extended == 1
    assert held.ends_at == T0 + timedelta(minutes=30 + 60)
    assert held.last_incident_id == second
    clock.advance(60 * 60 - 1)  # one second before the extended end
    assert response.revert_due() == []


def test_a_repeat_offender_gets_the_next_duration(response, freeze, clock):
    ends = []
    for n in range(4):
        incident_id = block(response, freeze, n)
        [held] = [c for c in response.containments_of(incident_id) if c.status == "active"]
        ends.append((held.offence, held.ends_at - held.started_at))
        clock.advance((held.ends_at - clock.now()).total_seconds())
        response.revert_due()
        clock.advance(10 * 60)  # back ten minutes after the block ended
    assert ends == [
        (1, timedelta(minutes=60)),
        (2, timedelta(minutes=120)),
        (3, timedelta(minutes=240)),
        (4, timedelta(minutes=240)),
    ]


def test_not_a_repeat_after_the_longest_duration_has_passed(response, freeze, clock):
    block(response, freeze, 0)
    clock.advance(60 * 60)
    response.revert_due()
    clock.advance(240 * 60 + 1)  # more than the longest duration after the end
    incident_id = block(response, freeze, 1)
    [held] = [c for c in response.containments_of(incident_id) if c.status == "active"]
    assert held.offence == 1


# ---- off ----------------------------------------------------------------------------------


def test_switched_off_nothing_is_recorded_or_reverted(db, clock, config, freeze):
    plain = ResponseEngine(db, clock, config, containment=ContainmentConfig("off", ()))
    incident_id = freeze(0, plain)
    plain.decide(incident_id, DecisionType.APPROVE, **ANALYST)
    clock.advance(24 * 60 * 60)
    assert plain.revert_due() == []
    assert plain.containments_of(incident_id) == []
