import json

import pytest
from pydantic import ValidationError

from app.contracts import AuditEventType, AuditRecord
from app.contracts.audit import INCIDENT_SCOPED_EVENT_TYPES, SIMULATED_EVENT_TYPES

REQUIRED = ["record_id", "occurred_at", "event_type", "actor", "result"]


@pytest.fixture
def data(load_example):
    return load_example("audit-record")


@pytest.fixture
def login_failed(data):
    data.update(
        event_type="auth.login_failed",
        actor="anonymous",
        actor_role=None,
        incident_id=None,
        result="failure",
        simulated=False,
        details={"reason": "unknown username"},
    )
    return data


def test_example_round_trips(data):
    record = AuditRecord.model_validate_json(json.dumps(data))
    assert AuditRecord.model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("field", REQUIRED)
def test_missing_required_field_is_rejected(data, field):
    del data[field]
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(data)


def test_event_types_copied_exactly():
    assert len(AuditEventType) == 21
    assert AuditEventType("response_window.opened") is AuditEventType.RESPONSE_WINDOW_OPENED
    assert AuditEventType("expiry_duplicate_ignored") is AuditEventType.EXPIRY_DUPLICATE_IGNORED


def test_unknown_event_type_is_rejected(data):
    data["event_type"] = "action.executed"
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(data)


@pytest.mark.parametrize("event_type", sorted(SIMULATED_EVENT_TYPES))
def test_simulated_types_require_simulated_true(data, event_type):
    data.update(event_type=event_type, simulated=False)
    with pytest.raises(ValidationError, match="simulated"):
        AuditRecord.model_validate(data)


def test_isolation_released_by_analyst_is_valid(data):
    data.update(event_type="isolation.released", actor="user-42", actor_role="soc_analyst")
    assert AuditRecord.model_validate(data).simulated is True


def test_other_types_require_simulated_false(data):
    data["event_type"] = "status_changed"
    with pytest.raises(ValidationError, match="simulated"):
        AuditRecord.model_validate(data)


def test_simulated_defaults_to_false(data):
    del data["simulated"]
    data["event_type"] = "status_changed"
    assert AuditRecord.model_validate(data).simulated is False


@pytest.mark.parametrize("event_type", sorted(INCIDENT_SCOPED_EVENT_TYPES))
def test_incident_scoped_types_require_incident_id(data, event_type):
    data.update(
        event_type=event_type,
        simulated=event_type in SIMULATED_EVENT_TYPES,
        incident_id=None,
    )
    with pytest.raises(ValidationError, match="requires incident_id"):
        AuditRecord.model_validate(data)


def test_failed_login_without_incident_is_valid(login_failed):
    record = AuditRecord.model_validate(login_failed)
    assert record.incident_id is None
    assert record.actor_role is None


def test_login_by_user_requires_role(login_failed):
    login_failed.update(event_type="auth.login_succeeded", actor="user-42", result="success")
    with pytest.raises(ValidationError, match="actor_role"):
        AuditRecord.model_validate(login_failed)


def test_login_by_user_with_role_is_valid(login_failed):
    login_failed.update(
        event_type="auth.login_succeeded",
        actor="user-42",
        actor_role="soc_manager",
        result="success",
    )
    assert AuditRecord.model_validate(login_failed).actor_role == "soc_manager"


@pytest.mark.parametrize("actor", ["system", "anonymous"])
def test_system_and_anonymous_have_no_role(login_failed, actor):
    login_failed.update(actor=actor, actor_role="system_administrator")
    with pytest.raises(ValidationError, match="actor_role"):
        AuditRecord.model_validate(login_failed)


def test_unknown_role_is_rejected(login_failed):
    login_failed.update(actor="user-42", actor_role="admin")
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(login_failed)


def test_extra_field_is_rejected(data):
    data["password"] = "hunter2"
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(data)


def test_naive_timestamp_is_rejected(data):
    data["occurred_at"] = "2026-03-14T10:04:01"
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(data)


def test_empty_optional_string_is_rejected(data):
    data["incident_id"] = ""
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(data)


def test_details_accept_only_json_scalars(data):
    data["details"] = {"targets": ["ws-17"]}
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(data)
