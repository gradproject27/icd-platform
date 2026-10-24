import json

import pytest
from pydantic import ValidationError

from app.contracts import ActionState, ResponseAction

REQUIRED = ["action_id", "incident_id", "scenario_id", "state", "trigger", "target", "proposed_at"]


@pytest.fixture
def data(load_example):
    return load_example("response-action")


@pytest.fixture
def proposed(data):
    """The example as a proposed action from an analyst, before any decision."""
    data.update(
        state="proposed",
        trigger=None,
        decided_by=None,
        decided_at=None,
        executed_at=None,
    )
    return data


def test_example_round_trips(data):
    action = ResponseAction.model_validate_json(json.dumps(data))
    assert ResponseAction.model_validate_json(action.model_dump_json()) == action


@pytest.mark.parametrize("field", REQUIRED)
def test_missing_required_field_is_rejected(data, field):
    del data[field]
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)


def test_proposed_action_is_valid(proposed):
    action = ResponseAction.model_validate(proposed)
    assert action.state == ActionState.PROPOSED
    assert action.trigger is None
    assert action.simulated is True


@pytest.mark.parametrize("trigger", ["analyst_decision", "window_expiry"])
def test_proposed_action_with_trigger_is_rejected(proposed, trigger):
    proposed["trigger"] = trigger
    with pytest.raises(ValidationError, match="proposed action requires"):
        ResponseAction.model_validate(proposed)


@pytest.mark.parametrize(
    ("field", "value"), [("decided_by", "user-42"), ("decided_at", "2026-03-14T10:03:30Z")]
)
def test_proposed_action_with_decision_is_rejected(proposed, field, value):
    proposed[field] = value
    with pytest.raises(ValidationError, match="proposed action requires"):
        ResponseAction.model_validate(proposed)


def test_simulated_false_is_rejected(data):
    data["simulated"] = False
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)


def test_unknown_scenario_is_rejected(data):
    data["scenario_id"] = "S5"
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)


def test_hyphenated_state_is_rejected(data):
    data["state"] = "simulated-succeeded"
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)


@pytest.mark.parametrize("scenario", ["S1", "S2", "S3", "S4"])
def test_every_scenario_requires_host(proposed, scenario):
    proposed.update(scenario_id=scenario, target={"ip": "203.0.113.7", "account": "svc-backup"})
    with pytest.raises(ValidationError, match="target.host"):
        ResponseAction.model_validate(proposed)


@pytest.mark.parametrize("scenario", ["S1", "S4"])
def test_host_only_scenarios_need_only_host(proposed, scenario):
    proposed.update(scenario_id=scenario, target={"host": "ws-17"})
    assert ResponseAction.model_validate(proposed).target.ip is None


def test_s2_requires_ip(proposed):
    proposed["target"] = {"host": "ws-17", "account": "svc-backup"}
    with pytest.raises(ValidationError, match="S2"):
        ResponseAction.model_validate(proposed)


def test_s3_requires_account(proposed):
    proposed.update(scenario_id="S3", target={"host": "ws-17", "ip": "203.0.113.7"})
    with pytest.raises(ValidationError, match="S3"):
        ResponseAction.model_validate(proposed)


def test_s3_with_account_is_valid(proposed):
    proposed.update(scenario_id="S3", target={"host": "ws-17", "account": "svc-backup"})
    assert ResponseAction.model_validate(proposed).target.account == "svc-backup"


def test_window_expiry_requires_system(data):
    data["decided_by"] = "user-42"
    with pytest.raises(ValidationError, match="window_expiry"):
        ResponseAction.model_validate(data)


def test_analyst_decision_by_user_is_valid(data):
    data.update(trigger="analyst_decision", decided_by="user-42", window_id=None)
    assert ResponseAction.model_validate(data).decided_by == "user-42"


@pytest.mark.parametrize("field", ["trigger", "decided_by", "decided_at"])
def test_decided_action_requires_decision_fields(data, field):
    data.update(trigger="analyst_decision", state="approved", executed_at=None)
    data[field] = None
    with pytest.raises(ValidationError, match="trigger, decided_by and decided_at"):
        ResponseAction.model_validate(data)


def test_approved_action_is_valid(data):
    data.update(trigger="analyst_decision", decided_by="user-42", state="approved")
    data["executed_at"] = None
    assert ResponseAction.model_validate(data).state == ActionState.APPROVED


@pytest.mark.parametrize("state", ["simulated_succeeded", "simulated_failed"])
def test_simulated_state_requires_executed_at(data, state):
    data.update(state=state, executed_at=None, failure_reason="executor timeout")
    with pytest.raises(ValidationError, match="executed_at"):
        ResponseAction.model_validate(data)


def test_simulated_failed_requires_failure_reason(data):
    data["state"] = "simulated_failed"
    with pytest.raises(ValidationError, match="failure_reason"):
        ResponseAction.model_validate(data)


def test_simulated_failed_with_reason_is_valid(data):
    data.update(state="simulated_failed", failure_reason="forced failure (test hook)")
    assert ResponseAction.model_validate(data).failure_reason is not None


def test_failure_reason_outside_simulated_failed_is_rejected(data):
    data["failure_reason"] = "executor timeout"
    with pytest.raises(ValidationError, match="failure_reason"):
        ResponseAction.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [("decided_at", "2026-03-14T10:02:59Z"), ("executed_at", "2026-03-14T10:03:59Z")],
)
def test_timestamps_out_of_order_are_rejected(data, field, value):
    data[field] = value
    with pytest.raises(ValidationError, match="proposed_at <= decided_at <= executed_at"):
        ResponseAction.model_validate(data)


def test_extra_field_is_rejected(data):
    data["real_execution"] = True
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)


def test_naive_timestamp_is_rejected(data):
    data["proposed_at"] = "2026-03-14T10:03:00"
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)


def test_parameters_accept_only_json_scalars(data):
    data["parameters"] = {"ports": [22, 443]}
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)


@pytest.mark.parametrize("field", ["comment", "failure_reason"])
def test_empty_optional_string_is_rejected(data, field):
    data[field] = ""
    with pytest.raises(ValidationError):
        ResponseAction.model_validate(data)
