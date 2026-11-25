"""Incident key facts (P1 of the competitor feature study, PR #51, F-I): computed by code from
the incident's flagged events, never by the model. C3's real correlation and risk over
fixtures/correlation/events.json, as in the response engine tests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import Event, EventRole, Incident
from app.correlation import correlate, load_config, load_risk_config, score_incidents
from app.incidents.key_facts import MAX_CITED, MAX_ITEMS, KeyFacts, key_facts
from app.response import load_response_config

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(e)
    for e in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
NOW = datetime(2026, 1, 15, 20, 20, tzinfo=UTC)
INCIDENTS = score_incidents(
    correlate(EVENTS, load_config(), NOW).incidents,
    EVENTS,
    evaluated_at=NOW,
    config=load_risk_config(assets_path=FIXTURES / "assets.toml"),
)
CONFIG = load_response_config()


def incident_starting(event_id: str) -> Incident:
    return next(i for i in INCIDENTS if i.events[0].event_id == event_id)


def values(items) -> list[str]:
    return [item.value for item in items]


@pytest.fixture
def facts_a() -> KeyFacts:
    # Fixture incident A: 8 flagged events from fx-002 to fx-013, 3 context events.
    return key_facts(incident_starting("fx-002"), EVENTS, CONFIG)


def test_start_and_end_come_from_the_first_and_last_flagged_event(facts_a):
    assert facts_a.first_flagged_event_id == "fx-002"
    assert facts_a.started_at == datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
    assert facts_a.last_flagged_event_id == "fx-013"
    assert facts_a.last_flagged_at == datetime(2026, 1, 15, 10, 8, tzinfo=UTC)
    assert facts_a.flagged_event_count == 8
    assert facts_a.context_event_count == 3


def test_started_on_and_origin(facts_a):
    # fx-002: host web-01, 203.0.113.10 (external) -> 10.10.1.21 (internal).
    assert facts_a.started_on == "web-01"
    assert facts_a.origin_ip == "203.0.113.10"


def test_attack_types_in_order_of_first_appearance_with_counts(facts_a):
    assert [(i.value, i.event_count) for i in facts_a.attack_types] == [
        ("Reconnaissance", 2),
        ("Exploits", 3),
        ("Backdoors", 3),
    ]
    assert facts_a.attack_types[0].event_ids == ["fx-002", "fx-004"]
    assert facts_a.attack_types[2].first_seen == datetime(2026, 1, 15, 9, 18, tzinfo=UTC)


def test_assets_indicators_ports_and_accounts(facts_a):
    assert values(facts_a.hosts) == ["web-01", "db-01", "file-01"]
    assert [i.event_count for i in facts_a.hosts] == [4, 3, 1]
    assert values(facts_a.internal_ips) == ["10.10.1.21", "10.10.2.31"]
    assert [i.event_count for i in facts_a.internal_ips] == [6, 2]
    # 203.0.113.10 is a documentation range Python calls private; response.toml says external.
    assert values(facts_a.external_ips) == ["203.0.113.10"]
    assert facts_a.external_ips[0].event_ids == ["fx-002", "fx-004", "fx-007", "fx-008"]
    assert values(facts_a.destination_ports) == ["443", "4444", "5432"]
    assert values(facts_a.accounts) == ["www-data", "svc-db"]
    assert facts_a.truncated is False


def test_context_events_never_count(facts_a):
    # Context fx-003 carries 10.10.5.5 and port 80; context fx-011/fx-014 only repeat svc-db.
    everything = [
        cited
        for items in (
            facts_a.attack_types,
            facts_a.hosts,
            facts_a.internal_ips,
            facts_a.external_ips,
            facts_a.destination_ports,
            facts_a.accounts,
        )
        for item in items
        for cited in item.event_ids
    ]
    assert not {"fx-003", "fx-011", "fx-014"} & set(everything)
    assert "10.10.5.5" not in values(facts_a.internal_ips)
    assert "80" not in values(facts_a.destination_ports)


def test_every_cited_event_is_a_flagged_event_of_the_incident(facts_a):
    incident = incident_starting("fx-002")
    flagged = {link.event_id for link in incident.events if link.role == EventRole.FLAGGED}
    for items in (facts_a.attack_types, facts_a.hosts, facts_a.external_ips):
        for item in items:
            assert set(item.event_ids) <= flagged
            assert len(item.event_ids) == min(item.event_count, MAX_CITED)


def test_incident_without_entities_has_empty_lists():
    facts = key_facts(incident_starting("fx-005"), EVENTS, CONFIG)
    assert facts.started_on is None
    assert facts.origin_ip is None
    assert values(facts.attack_types) == ["Generic"]
    assert facts.hosts == facts.internal_ips == facts.external_ips == []
    assert facts.destination_ports == facts.accounts == []


def test_hostless_start_falls_back_to_the_internal_destination():
    hostless = [e.model_copy(update={"host": None}) for e in EVENTS]
    facts = key_facts(incident_starting("fx-002"), hostless, CONFIG)
    assert facts.started_on == "10.10.1.21"
    assert facts.hosts == []


def test_internal_source_is_not_an_origin():
    # fx-008 runs web-01 -> 203.0.113.10; started from it, the origin must stay null.
    incident = incident_starting("fx-002")
    later = [
        e.model_copy(update={"timestamp": e.timestamp + timedelta(hours=1)})
        if e.event_id in {"fx-002", "fx-004", "fx-007"}
        else e
        for e in EVENTS
    ]
    facts = key_facts(incident, later, CONFIG)
    assert facts.first_flagged_event_id == "fx-008"
    assert facts.origin_ip is None


def test_same_input_gives_the_same_facts_in_any_event_order(facts_a):
    assert key_facts(incident_starting("fx-002"), list(reversed(EVENTS)), CONFIG) == facts_a


def test_lists_are_capped_and_marked_truncated():
    incident = incident_starting("fx-002")
    flagged = [link.event_id for link in incident.events if link.role == EventRole.FLAGGED]
    # Give each flagged event many distinct destination ports by cloning it.
    events = list(EVENTS)
    links = list(incident.events)
    for n in range(MAX_ITEMS + 5):
        clone = next(e for e in EVENTS if e.event_id == flagged[0]).model_copy(
            update={"event_id": f"fx-clone-{n:02d}", "dst_port": 10000 + n}
        )
        events.append(clone)
        links.append(links[0].model_copy(update={"event_id": clone.event_id}))
    bigger = incident.model_copy(update={"events": links})
    facts = key_facts(bigger, events, CONFIG)
    assert len(facts.destination_ports) == MAX_ITEMS
    assert facts.truncated is True
    assert facts.attack_types[0].event_count == 2 + MAX_ITEMS + 5
    assert len(facts.attack_types[0].event_ids) == MAX_CITED


def test_missing_event_is_an_error():
    with pytest.raises(ValueError, match="events missing"):
        key_facts(incident_starting("fx-002"), EVENTS[:3], CONFIG)


def test_config_version_is_recorded(facts_a):
    assert facts_a.network_config_version == CONFIG.config_version
    assert facts_a.tactics_config_version == "tactics-v1"


def test_tactics_come_from_the_table_with_their_events(facts_a):
    # P4: Reconnaissance -> TA0043; Exploits -> TA0001; Backdoors -> TA0003 and TA0011.
    assert [(i.value, i.event_count) for i in facts_a.tactics] == [
        ("TA0043 Reconnaissance", 2),
        ("TA0001 Initial Access", 3),
        ("TA0003 Persistence", 3),
        ("TA0011 Command and Control", 3),
    ]
    assert facts_a.tactics[0].event_ids == ["fx-002", "fx-004"]


def test_an_attack_type_without_a_tactic_gives_none():
    # fx-005 is labelled Generic, which the table leaves unmapped.
    assert key_facts(incident_starting("fx-005"), EVENTS, CONFIG).tactics == []
