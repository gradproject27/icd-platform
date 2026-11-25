"""ECS export of stored events (P7 of the competitor feature study, F-J).

An export view only: ICD's Event contract keeps its own names. Every ECS field written must exist
in the pinned ECS release (9.5.0); ICD's own fields go under `icd.`.
"""

import json
from pathlib import Path

from app.contracts import Event
from app.ingest.ecs_export import ECS_FIELDS, ECS_VERSION, to_ecs

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = {
    e["event_id"]: Event.model_validate(e)
    for e in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
}


def paths(doc: dict, prefix: str = "") -> set[str]:
    out = set()
    for key, value in doc.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out |= paths(value, f"{path}.")
        else:
            out.add(path)
    return out


def test_flagged_event_maps_to_ecs_fields():
    doc = to_ecs(EVENTS["fx-007"])  # flagged Exploits, web-01, 203.0.113.10 -> 10.10.1.21:443
    assert doc["@timestamp"] == "2026-01-15T09:10:00Z"
    assert doc["ecs"] == {"version": "9.5.0"}
    assert doc["event"]["id"] == "fx-007"
    assert doc["event"]["kind"] == "alert"  # flagged by the dataset label
    assert doc["event"]["dataset"] == EVENTS["fx-007"].provenance.dataset_id
    assert doc["host"] == {"name": "web-01"}
    assert doc["source"]["ip"] == "203.0.113.10"
    assert doc["destination"] == {"ip": "10.10.1.21", "port": 443}
    assert doc["user"] == {"name": "www-data"}
    assert doc["message"] == EVENTS["fx-007"].summary
    assert doc["threat"] == {
        "framework": "MITRE ATT&CK",
        "tactic": {"id": ["TA0001"], "name": ["Initial Access"]},
    }
    assert doc["icd"]["label"] == {"status": "flagged", "attack_type": "Exploits"} | {
        k: v for k, v in {"raw_value": EVENTS["fx-007"].label.raw_value}.items() if v is not None
    }


def test_context_event_is_an_event_without_threat():
    doc = to_ecs(EVENTS["fx-003"])  # unflagged context
    assert doc["event"]["kind"] == "event"
    assert "threat" not in doc
    assert doc["icd"]["label"]["status"] == "unflagged"


def test_every_ecs_path_is_in_the_pinned_release_and_nulls_are_left_out():
    assert ECS_VERSION == "9.5.0"
    for event in EVENTS.values():
        doc = to_ecs(event)
        ecs_paths = {p for p in paths(doc) if not p.startswith("icd.")}
        assert ecs_paths <= ECS_FIELDS, ecs_paths - ECS_FIELDS
        assert None not in [v for v in _leaves(doc)]


def _leaves(doc):
    for value in doc.values():
        if isinstance(value, dict):
            yield from _leaves(value)
        else:
            yield value


def test_transport_or_application_protocol():
    tcp = EVENTS["fx-007"].model_copy(update={"protocol": "TCP"})
    assert to_ecs(tcp)["network"] == {"transport": "tcp"}
    http = EVENTS["fx-007"].model_copy(update={"protocol": "http"})
    assert to_ecs(http)["network"] == {"protocol": "http"}


def test_the_event_is_not_changed():
    event = EVENTS["fx-007"]
    before = event.model_dump()
    to_ecs(event)
    assert event.model_dump() == before
