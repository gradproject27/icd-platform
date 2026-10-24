import json

import pytest
from pydantic import ValidationError

from app.contracts import Incident, IncidentStatus

REQUIRED = [
    "incident_id",
    "created_at",
    "updated_at",
    "first_event_at",
    "last_event_at",
    "events",
]


@pytest.fixture
def data(load_example):
    return load_example("incident")


def test_example_round_trips(data):
    incident = Incident.model_validate_json(json.dumps(data))
    assert Incident.model_validate_json(incident.model_dump_json()) == incident


@pytest.mark.parametrize("field", REQUIRED)
def test_missing_required_field_is_rejected(data, field):
    del data[field]
    with pytest.raises(ValidationError):
        Incident.model_validate(data)


def test_defaults_for_a_new_incident(data):
    for field in ("status", "risk", "analysis_status", "analysis_attempts"):
        del data[field]
    data["latest_report_id"] = None
    data["confidence"] = None
    incident = Incident.model_validate(data)
    assert incident.status == IncidentStatus.NEW
    assert incident.risk is None
    assert incident.analysis_attempts == 0


def test_updated_at_before_created_at_is_rejected(data):
    data["updated_at"] = "2026-03-14T10:00:00Z"
    with pytest.raises(ValidationError, match="updated_at"):
        Incident.model_validate(data)


def test_last_event_before_first_event_is_rejected(data):
    data["last_event_at"] = "2026-03-14T09:00:00Z"
    with pytest.raises(ValidationError, match="last_event_at"):
        Incident.model_validate(data)


def test_duplicate_event_ids_are_rejected(data):
    data["events"][1]["event_id"] = "evt-0001"
    with pytest.raises(ValidationError, match="unique"):
        Incident.model_validate(data)


def test_context_only_incident_is_rejected(data):
    for link in data["events"]:
        link["role"] = "context"
    with pytest.raises(ValidationError, match="at least one flagged"):
        Incident.model_validate(data)


def test_one_flagged_event_is_enough(data):
    data["events"] = data["events"][:1]
    assert len(Incident.model_validate(data).events) == 1


def test_only_the_first_event_may_have_no_link_keys(data):
    data["events"][1]["link_keys"] = []
    with pytest.raises(ValidationError, match="link_keys"):
        Incident.model_validate(data)


def test_confidence_without_succeeded_analysis_is_rejected(data):
    data["analysis_status"] = "failed"
    with pytest.raises(ValidationError, match="confidence"):
        Incident.model_validate(data)


def test_failed_analysis_without_confidence_is_valid(data):
    data["analysis_status"] = "failed"
    data["confidence"] = None
    assert Incident.model_validate(data).confidence is None


def test_succeeded_analysis_requires_confidence(data):
    data["confidence"] = None
    with pytest.raises(ValidationError, match="confidence"):
        Incident.model_validate(data)


def test_succeeded_analysis_requires_report_id(data):
    data["latest_report_id"] = None
    with pytest.raises(ValidationError, match="latest_report_id"):
        Incident.model_validate(data)


def test_detected_status_is_rejected(data):
    data["status"] = "detected"
    with pytest.raises(ValidationError):
        Incident.model_validate(data)


def test_status_display_labels():
    assert IncidentStatus.NEW.label == "New"
    assert IncidentStatus.RESPONSE_IN_PROGRESS.label == "Response in Progress"
    assert all(status.label for status in IncidentStatus)


def test_risk_score_above_100_is_rejected(data):
    data["risk"]["score"] = 101
    with pytest.raises(ValidationError):
        Incident.model_validate(data)


def test_risk_without_factors_is_rejected(data):
    data["risk"]["factors"] = []
    with pytest.raises(ValidationError):
        Incident.model_validate(data)


def test_level_is_not_tied_to_score(data):
    # Thresholds are configurable (FR-20); C3's scoring code enforces them.
    data["risk"]["level"] = "low"
    assert Incident.model_validate(data).risk.level == "low"


def test_incident_without_events_is_rejected(data):
    data["events"] = []
    with pytest.raises(ValidationError):
        Incident.model_validate(data)


def test_extra_field_is_rejected(data):
    data["risk_score"] = 74
    with pytest.raises(ValidationError):
        Incident.model_validate(data)


def test_naive_timestamp_is_rejected(data):
    data["created_at"] = "2026-03-14T10:00:30"
    with pytest.raises(ValidationError):
        Incident.model_validate(data)


def test_empty_optional_string_is_rejected(data):
    data["incident_type"] = ""
    with pytest.raises(ValidationError):
        Incident.model_validate(data)
