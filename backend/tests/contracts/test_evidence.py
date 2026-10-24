import json

import pytest
from pydantic import ValidationError

from app.contracts import EvidencePackage

REQUIRED = [
    "package_id",
    "incident_id",
    "created_at",
    "incident",
    "events",
    "total_event_count",
    "truncated",
]


@pytest.fixture
def data(load_example):
    return load_example("evidence-package")


def test_example_round_trips(data):
    package = EvidencePackage.model_validate_json(json.dumps(data))
    assert EvidencePackage.model_validate_json(package.model_dump_json()) == package


@pytest.mark.parametrize("field", REQUIRED)
def test_missing_required_field_is_rejected(data, field):
    del data[field]
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(data)


def test_masked_defaults_to_true(data):
    del data["masked"]
    assert EvidencePackage.model_validate(data).masked is True


def test_citable_event_ids(data):
    package = EvidencePackage.model_validate(data)
    assert package.citable_event_ids() == {"evt-0001", "evt-0002", "evt-0003", "evt-0004"}


def test_duplicate_event_ids_are_rejected(data):
    data["events"][1]["event_id"] = "evt-0001"
    with pytest.raises(ValidationError, match="unique"):
        EvidencePackage.model_validate(data)


def test_more_events_than_total_is_rejected(data):
    data["total_event_count"] = 3
    with pytest.raises(ValidationError, match="total_event_count"):
        EvidencePackage.model_validate(data)


def test_truncated_without_missing_events_is_rejected(data):
    data["truncated"] = True
    with pytest.raises(ValidationError, match="truncated"):
        EvidencePackage.model_validate(data)


def test_missing_events_without_truncated_is_rejected(data):
    data["total_event_count"] = 80
    with pytest.raises(ValidationError, match="truncated"):
        EvidencePackage.model_validate(data)


def test_truncated_package_is_valid(data):
    data["total_event_count"] = 80
    data["truncated"] = True
    assert EvidencePackage.model_validate(data).truncated is True


def test_context_before_flagged_is_rejected(data):
    data["events"] = [data["events"][3], *data["events"][:3]]
    with pytest.raises(ValidationError, match="flagged events must come before"):
        EvidencePackage.model_validate(data)


@pytest.mark.parametrize(
    ("index", "label_status"),
    [(0, "unflagged"), (0, "unlabelled"), (3, "flagged")],
)
def test_role_and_label_must_agree(data, index, label_status):
    data["events"][index]["label_status"] = label_status
    with pytest.raises(ValidationError, match="label_status"):
        EvidencePackage.model_validate(data)


def test_unlabelled_context_event_is_valid(data):
    data["events"][3]["label_status"] = "unlabelled"
    assert EvidencePackage.model_validate(data).events[3].label_status == "unlabelled"


def test_51_events_are_rejected(data):
    template = data["events"][0]
    data["events"] = [{**template, "event_id": f"evt-{i:04d}"} for i in range(51)]
    data["total_event_count"] = 51
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(data)


def test_50_events_are_accepted(data):
    template = data["events"][0]
    data["events"] = [{**template, "event_id": f"evt-{i:04d}"} for i in range(50)]
    data["total_event_count"] = 60
    data["truncated"] = True
    assert len(EvidencePackage.model_validate(data).events) == 50


def test_extra_field_is_rejected(data):
    data["events"][0]["raw_line"] = "Mar 14 09:12:05 sshd[1]: Failed password"
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(data)


def test_naive_timestamp_is_rejected(data):
    data["created_at"] = "2026-03-14T10:01:00"
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(data)


def test_empty_optional_string_is_rejected(data):
    data["events"][0]["host"] = ""
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(data)
