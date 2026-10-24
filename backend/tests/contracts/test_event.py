import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contracts import Event, LabelStatus

REQUIRED = ["event_id", "timestamp", "ingested_at", "event_type", "label", "summary", "provenance"]


@pytest.fixture
def data(load_example):
    return load_example("event")


def test_example_round_trips(data):
    event = Event.model_validate_json(json.dumps(data))
    assert Event.model_validate_json(event.model_dump_json()) == event


@pytest.mark.parametrize("field", REQUIRED)
def test_missing_required_field_is_rejected(data, field):
    del data[field]
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_missing_optional_values_are_null(data):
    for field in ("host", "src_ip", "dst_ip", "src_port", "dst_port", "protocol", "user"):
        del data[field]
    event = Event.model_validate(data)
    assert event.host is None
    assert json.loads(event.model_dump_json())["src_ip"] is None


@pytest.mark.parametrize(
    ("status", "raw_value"),
    [("unlabelled", "malicious"), ("flagged", None), ("unflagged", None)],
)
def test_label_status_must_match_raw_value(data, status, raw_value):
    data["label"] = {"status": status, "raw_value": raw_value}
    with pytest.raises(ValidationError, match="unlabelled exactly when raw_value is null"):
        Event.model_validate(data)


def test_missing_label_is_unlabelled(data):
    data["label"] = {"status": "unlabelled", "raw_value": None}
    event = Event.model_validate(data)
    assert event.label.status == LabelStatus.UNLABELLED
    assert event.label.origin == "dataset"


def test_label_origin_is_always_dataset(data):
    data["label"]["origin"] = "model"
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_extra_field_is_rejected(data):
    data["severity"] = "high"
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_naive_timestamp_is_rejected(data):
    data["timestamp"] = "2026-03-14T09:12:05"
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_timestamp_is_converted_to_utc(data):
    data["timestamp"] = "2026-03-14T12:12:05+03:00"
    event = Event.model_validate(data)
    assert event.timestamp == datetime(2026, 3, 14, 9, 12, 5, tzinfo=UTC)
    assert event.timestamp.tzinfo == UTC
    assert json.loads(event.model_dump_json())["timestamp"] == "2026-03-14T09:12:05Z"


@pytest.mark.parametrize("field", ["host", "protocol", "user"])
def test_empty_optional_string_is_rejected(data, field):
    data[field] = ""
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_invalid_ip_is_rejected(data):
    data["src_ip"] = "999.1.1.1"
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_out_of_range_port_is_rejected(data):
    data["dst_port"] = 65536
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_summary_longer_than_500_is_rejected(data):
    data["summary"] = "x" * 501
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_extra_fields_accept_only_json_scalars(data):
    data["extra_fields"] = {"nested": {"a": 1}}
    with pytest.raises(ValidationError):
        Event.model_validate(data)


def test_event_is_immutable(data):
    event = Event.model_validate(data)
    with pytest.raises(ValidationError):
        event.host = "ws-18"
