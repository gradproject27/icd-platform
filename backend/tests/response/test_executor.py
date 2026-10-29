"""Simulated executor (FR-45, NFR-SF-01, NFR-SF-07, AS-19): simulated only, failure path tested."""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import app.response as response_package
from app.contracts import ActionState, ActionTrigger, ScenarioId
from app.response import SIMULATED_LABEL, MissingTarget, Targets, decide, execute, propose

T0 = datetime(2026, 1, 15, 20, 20, tzinfo=UTC)
TARGETS = Targets(host="web-01", source_ip="203.0.113.10", account="svc-db")


def approved(scenario: ScenarioId, *, isolated=True, targets=TARGETS):
    action = propose(
        action_id="act-1",
        incident_id="inc-1",
        scenario_id=scenario,
        targets=targets,
        isolated=isolated,
        now=T0,
        window_id="win-1",
    )
    return decide(
        action,
        trigger=ActionTrigger.WINDOW_EXPIRY,
        decided_by="system",
        now=T0 + timedelta(seconds=1),
    )


@pytest.mark.parametrize(
    ("scenario", "expected", "isolated_after"),
    [
        (ScenarioId.S1, {"isolation": "kept", "investigation_flag": True}, True),
        (ScenarioId.S2, {"isolation": "kept", "block_ip": "203.0.113.10"}, True),
        (ScenarioId.S3, {"isolation": "kept", "disable_account": "svc-db"}, True),
        (ScenarioId.S4, {"isolation": "released", "monitoring": "raised"}, False),
    ],
)
def test_each_scenario_is_simulated(scenario, expected, isolated_after):
    result = execute(approved(scenario), isolated=True, now=T0 + timedelta(seconds=2))
    action = result.action
    assert result.succeeded and action.state == ActionState.SIMULATED_SUCCEEDED
    assert action.simulated is True
    assert action.parameters["label"] == SIMULATED_LABEL
    assert expected.items() <= action.parameters.items()
    assert result.isolated_after is isolated_after


def test_s1_isolates_a_host_that_is_not_isolated_yet():
    action = approved(ScenarioId.S1, isolated=False)
    assert action.parameters["isolation"] == "applied"


def test_injected_failure_is_recorded_and_changes_nothing():
    result = execute(
        approved(ScenarioId.S2),
        isolated=False,
        now=T0 + timedelta(seconds=2),
        failure_rule=lambda action: "simulated executor failure",
    )
    assert not result.succeeded
    assert result.action.state == ActionState.SIMULATED_FAILED
    assert result.action.failure_reason == "simulated executor failure"
    assert result.isolated_after is False


def test_only_approved_actions_run():
    proposed = propose(
        action_id="a", incident_id="i", scenario_id=ScenarioId.S1, targets=TARGETS,
        isolated=True, now=T0,
    )  # fmt: skip
    with pytest.raises(ValueError, match="only an approved action"):
        execute(proposed, isolated=True, now=T0)


@pytest.mark.parametrize(
    ("scenario", "targets", "message"),
    [
        (ScenarioId.S1, Targets(None, None, None), "host"),
        (ScenarioId.S2, Targets("h", None, "a"), "source IP"),
        (ScenarioId.S3, Targets("h", "1.2.3.4", None), "account"),
    ],
)
def test_missing_target_refused_before_anything_runs(scenario, targets, message):
    with pytest.raises(MissingTarget, match=message):
        propose(
            action_id="a", incident_id="i", scenario_id=scenario, targets=targets,
            isolated=False, now=T0,
        )  # fmt: skip


FORBIDDEN_MODULES = {
    "socket", "ssl", "subprocess", "http", "urllib", "httpx", "requests", "paramiko",
    "ftplib", "smtplib", "telnetlib", "asyncio", "multiprocessing", "ctypes", "os",
}  # fmt: skip


def test_response_package_cannot_reach_a_real_system():
    """AS-19: no module of the engine core imports anything that could reach a network or shell."""
    package = Path(response_package.__file__).parent
    core = ["catalogue.py", "config.py", "executor.py", "freeze.py", "lifecycle.py", "targets.py"]
    for name in core:
        tree = ast.parse((package / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots = {(node.module or "").split(".")[0]}
            else:
                continue
            assert not roots & FORBIDDEN_MODULES, f"{name} imports {roots & FORBIDDEN_MODULES}"
