"""Simulated Response Executor (FR-45, NFR-SF-01, NFR-SF-07, C-13; response spec section 9).

It is a simulator: it builds a record of what the scenario would do and returns it marked
simulated. It imports nothing that can reach a network, a shell or another host, and a test
checks that. Nothing here changes a real machine, IP block list or account.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.contracts import (
    ActionState,
    ActionTarget,
    ActionTrigger,
    ResponseAction,
    ScenarioId,
)
from app.response.targets import Targets

SIMULATED_LABEL = "SIMULATED"

# Returns a failure reason to make the simulation fail, or None. Only tests pass one (D6).
FailureRule = Callable[[ResponseAction], str | None]


def never_fail(action: ResponseAction) -> str | None:
    return None


class MissingTarget(ValueError):
    """The scenario needs a target the incident does not have (spec open question 15)."""


def parameters_for(
    scenario_id: ScenarioId, targets: Targets, *, isolated: bool
) -> dict[str, str | bool]:
    """What the simulated action does, as data. `isolated` is the host's current state."""
    params: dict[str, str | bool] = {"label": SIMULATED_LABEL}
    if scenario_id == ScenarioId.S4:
        params.update(isolation="released", monitoring="raised")
        return params
    params["isolation"] = "kept" if isolated else "applied"
    if scenario_id == ScenarioId.S1:
        params["investigation_flag"] = True
    elif scenario_id == ScenarioId.S2:
        params["block_ip"] = targets.source_ip or ""
    elif scenario_id == ScenarioId.S3:
        params["disable_account"] = targets.account or ""
    return params


def propose(
    *,
    action_id: str,
    incident_id: str,
    scenario_id: ScenarioId,
    targets: Targets,
    isolated: bool,
    now: datetime,
    window_id: str | None = None,
) -> ResponseAction:
    """A proposed action for a scenario. Raises MissingTarget when a needed target is missing."""
    if targets.host is None:
        raise MissingTarget("every scenario needs a target host")
    if scenario_id == ScenarioId.S2 and targets.source_ip is None:
        raise MissingTarget("S2 needs an external source IP")
    if scenario_id == ScenarioId.S3 and targets.account is None:
        raise MissingTarget("S3 needs an involved account")
    return ResponseAction(
        action_id=action_id,
        incident_id=incident_id,
        scenario_id=scenario_id,
        state=ActionState.PROPOSED,
        window_id=window_id,
        target=ActionTarget(
            host=targets.host,
            ip=targets.source_ip if scenario_id == ScenarioId.S2 else None,
            account=targets.account if scenario_id == ScenarioId.S3 else None,
        ),
        parameters=parameters_for(scenario_id, targets, isolated=isolated),
        proposed_at=now,
    )


def decide(
    action: ResponseAction,
    *,
    trigger: ActionTrigger,
    decided_by: str,
    now: datetime,
    comment: str | None = None,
) -> ResponseAction:
    """The action, approved by an analyst or selected by the system on expiry."""
    return ResponseAction.model_validate(
        action.model_dump()
        | {
            "state": ActionState.APPROVED,
            "trigger": trigger,
            "decided_by": decided_by,
            "decided_at": now,
            "comment": comment,
        }
    )


@dataclass(frozen=True)
class SimulationResult:
    action: ResponseAction
    isolated_after: bool  # the host's simulated isolation state after the action

    @property
    def succeeded(self) -> bool:
        return self.action.state == ActionState.SIMULATED_SUCCEEDED


def execute(
    action: ResponseAction,
    *,
    isolated: bool,
    now: datetime,
    failure_rule: FailureRule = never_fail,
) -> SimulationResult:
    """Simulate an approved action. Changes nothing outside the returned record."""
    if action.state != ActionState.APPROVED:
        raise ValueError(f"only an approved action can be simulated, not {action.state}")
    reason = failure_rule(action)
    state = ActionState.SIMULATED_FAILED if reason else ActionState.SIMULATED_SUCCEEDED
    done = ResponseAction.model_validate(
        action.model_dump() | {"state": state, "executed_at": now, "failure_reason": reason}
    )
    if reason:
        return SimulationResult(done, isolated_after=isolated)
    return SimulationResult(done, isolated_after=action.scenario_id != ScenarioId.S4)
