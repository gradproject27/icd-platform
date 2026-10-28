import json
import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import Event, EventRole, IncidentStatus
from app.correlation import CorrelationConfig, correlate, incident_id_for, load_config

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(e)
    for e in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
EXPECTED = json.loads((FIXTURES / "expected-incidents.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 1, 16, tzinfo=UTC)
CONFIG = load_config()
T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def ev(n, minutes, status="flagged", attack=None, **fields):
    raw = {"flagged": "1", "unflagged": "0", "unlabelled": None}[status]
    return Event.model_validate(
        {
            "event_id": f"t-{n:03d}",
            "timestamp": (T0 + timedelta(minutes=minutes)).isoformat(),
            "ingested_at": NOW.isoformat(),
            "event_type": "unknown",
            "label": {"status": status, "raw_value": raw, "attack_type": attack},
            "summary": "test event",
            "provenance": {
                "dataset_id": "test",
                "source_file": "test.json",
                "record_ref": str(n),
                "source_format": "json",
            },
            **fields,
        }
    )


def groups(result):
    return [[link.event_id for link in inc.events] for inc in result.incidents]


# --- the shared fixture ---------------------------------------------------------------------


def test_fixture_gives_the_expected_incidents():
    result = correlate(EVENTS, CONFIG, NOW)
    assert len(result.incidents) == len(EXPECTED["incidents"])
    for inc, exp in zip(result.incidents, EXPECTED["incidents"], strict=True):
        assert inc.incident_id == incident_id_for(exp["start_event_id"]), exp["label"]
        flagged = [link for link in inc.events if link.role == EventRole.FLAGGED]
        context = [link for link in inc.events if link.role == EventRole.CONTEXT]
        as_rows = lambda links: [  # noqa: E731
            {"event_id": link.event_id, "link_keys": [k.value for k in link.link_keys]}
            for link in links
        ]
        assert as_rows(flagged) == exp["flagged"], exp["label"]
        assert as_rows(context) == exp["context"], exp["label"]
        assert inc.first_event_at == datetime.fromisoformat(exp["first_event_at"])
        assert inc.last_event_at == datetime.fromisoformat(exp["last_event_at"])
        assert inc.incident_type == exp["incident_type"], exp["label"]
        assert inc.status == IncidentStatus.NEW
        assert inc.risk is None
        assert inc.created_at == inc.updated_at == NOW
    outside = sorted(row["event_id"] for row in EXPECTED["not_in_any_incident"])
    assert list(result.unassigned_event_ids) == outside


# --- determinism (AS-04) --------------------------------------------------------------------


def _dump(result):
    return [inc.model_dump_json() for inc in result.incidents], result.unassigned_event_ids


def test_same_input_gives_identical_output():
    assert _dump(correlate(EVENTS, CONFIG, NOW)) == _dump(correlate(EVENTS, CONFIG, NOW))


@pytest.mark.parametrize("seed", range(20))
def test_input_order_does_not_matter(seed):
    shuffled = list(EVENTS)
    random.Random(seed).shuffle(shuffled)
    assert _dump(correlate(shuffled, CONFIG, NOW)) == _dump(correlate(EVENTS, CONFIG, NOW))


def test_now_is_injected_not_read_from_the_clock():
    later = NOW + timedelta(days=3)
    result = correlate(EVENTS, CONFIG, later)
    assert {inc.created_at for inc in result.incidents} == {later}
    assert {link.linked_at for inc in result.incidents for link in inc.events} == {later}


# --- edge cases -----------------------------------------------------------------------------


def test_empty_input():
    result = correlate([], CONFIG, NOW)
    assert result.incidents == () and result.unassigned_event_ids == ()


def test_single_flagged_event_is_an_incident_of_one():
    result = correlate([ev(1, 0, host="ws-1")], CONFIG, NOW)
    assert groups(result) == [["t-001"]]
    assert result.incidents[0].events[0].link_keys == []


def test_single_unflagged_event_creates_nothing():
    result = correlate([ev(1, 0, "unflagged", host="ws-1")], CONFIG, NOW)
    assert result.incidents == () and result.unassigned_event_ids == ("t-001",)


def test_window_boundary_is_inclusive():
    exact = [ev(1, 0, host="a"), ev(2, 15, host="a")]
    over = [
        ev(3, 0, host="b"),
        Event.model_validate(
            {
                **ev(4, 15, host="b").model_dump(mode="json"),
                "timestamp": (T0 + timedelta(minutes=15, seconds=1)).isoformat(),
            }
        ),
    ]
    assert groups(correlate(exact + over, CONFIG, NOW)) == [
        ["t-001", "t-002"],
        ["t-003"],
        ["t-004"],
    ]


def test_chaining_links_events_further_apart_than_the_window():
    events = [ev(1, 0, host="a"), ev(2, 10, host="a"), ev(3, 20, host="a")]
    assert groups(correlate(events, CONFIG, NOW)) == [["t-001", "t-002", "t-003"]]


def test_event_that_bridges_two_chains_merges_them():
    events = [ev(1, 0, host="a"), ev(2, 2, user="u"), ev(3, 5, host="a", user="u")]
    (incident,) = correlate(events, CONFIG, NOW).incidents
    keys = {link.event_id: [k.value for k in link.link_keys] for link in incident.events}
    # t-002 started its own chain; it lists the key t-003 linked it by, so that only the
    # starting event t-001 has no link_keys (contract rule).
    assert keys == {"t-001": [], "t-002": ["user"], "t-003": ["host", "user"]}


def test_ip_pair_is_unordered():
    events = [
        ev(1, 0, src_ip="10.0.0.1", dst_ip="10.0.0.2"),
        ev(2, 5, src_ip="10.0.0.2", dst_ip="10.0.0.1"),
    ]
    result = correlate(events, CONFIG, NOW)
    assert groups(result) == [["t-001", "t-002"]]
    assert [k.value for k in result.incidents[0].events[1].link_keys] == ["ip_pair"]


def test_only_one_ip_gives_no_ip_pair_key():
    events = [ev(1, 0, src_ip="10.0.0.1"), ev(2, 5, src_ip="10.0.0.1")]
    assert groups(correlate(events, CONFIG, NOW)) == [["t-001"], ["t-002"]]


def test_host_and_user_are_normalized():
    events = [ev(1, 0, host=" WS-1 ", user="Admin"), ev(2, 5, host="ws-1", user="admin ")]
    result = correlate(events, CONFIG, NOW)
    assert [k.value for k in result.incidents[0].events[1].link_keys] == ["host", "user"]


def test_event_type_is_not_a_key():
    a = ev(1, 0, host="a")
    b = ev(2, 5, host="b")
    assert a.event_type == b.event_type
    assert groups(correlate([a, b], CONFIG, NOW)) == [["t-001"], ["t-002"]]


def test_denylisted_value_never_links():
    config = replace(CONFIG, denied_users=frozenset({"system"}))
    events = [ev(1, 0, user="SYSTEM"), ev(2, 5, user="system")]
    assert groups(correlate(events, config, NOW)) == [["t-001"], ["t-002"]]
    assert groups(correlate(events, CONFIG, NOW)) == [["t-001", "t-002"]]


def test_duplicate_event_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        correlate([ev(1, 0, host="a"), ev(1, 5, host="a")], CONFIG, NOW)


# --- context events -------------------------------------------------------------------------


def test_context_never_merges_groups():
    events = [
        ev(1, 0, host="a"),
        ev(2, 0, host="b"),
        ev(3, 5, "unflagged", host="a", user="u"),
        ev(4, 6, "unlabelled", host="b", user="u"),
    ]
    result = correlate(events, CONFIG, NOW)
    assert groups(result) == [["t-001", "t-003"], ["t-002", "t-004"]]


def test_context_tie_goes_to_the_earliest_group():
    events = [ev(1, 0, host="a"), ev(2, 10, user="u"), ev(3, 5, "unflagged", host="a", user="u")]
    result = correlate(events, CONFIG, NOW)
    assert groups(result) == [["t-001", "t-003"], ["t-002"]]


def test_context_alone_never_creates_an_incident():
    events = [ev(1, 0, "unflagged", host="a"), ev(2, 1, "unlabelled", host="a")]
    result = correlate(events, CONFIG, NOW)
    assert result.incidents == () and result.unassigned_event_ids == ("t-001", "t-002")


def test_context_never_uses_the_escalated_window():
    events = [ev(1, 0, attack="Exploits", host="a"), ev(2, 20, "unflagged", host="a")]
    result = correlate(events, CONFIG, NOW)
    assert groups(result) == [["t-001"]] and result.unassigned_event_ids == ("t-002",)


# --- adaptive memory and kill-chain stages (team decision, 28 Oct 2026) -----------------------


def test_stage_two_extends_the_window_for_that_key_value():
    events = [ev(1, 0, attack="Exploits", host="a"), ev(2, 20, attack="Reconnaissance", host="a")]
    assert groups(correlate(events, CONFIG, NOW)) == [["t-001", "t-002"]]


def test_reconnaissance_alone_keeps_the_base_window():
    events = [ev(1, 0, attack="Reconnaissance", host="a"), ev(2, 20, attack="Exploits", host="a")]
    assert groups(correlate(events, CONFIG, NOW)) == [["t-001"], ["t-002"]]


def test_escalated_window_is_inclusive_and_bounded():
    linked = [ev(1, 0, attack="Exploits", host="a"), ev(2, 30, host="a")]
    apart = [ev(3, 0, attack="Exploits", host="b"), ev(4, 31, host="b")]
    assert groups(correlate(linked + apart, CONFIG, NOW)) == [
        ["t-001", "t-002"],
        ["t-003"],
        ["t-004"],
    ]


def test_memory_ends_when_the_chain_breaks():
    events = [
        ev(1, 0, attack="Exploits", host="a"),
        ev(2, 40, attack="Reconnaissance", host="a"),
        ev(3, 60, attack="Reconnaissance", host="a"),
    ]
    assert groups(correlate(events, CONFIG, NOW)) == [["t-001"], ["t-002"], ["t-003"]]


def test_memory_is_per_key_value():
    events = [
        ev(1, 0, attack="Exploits", host="a"),
        ev(2, 10, attack="Reconnaissance", host="a", user="u"),
        ev(3, 30, attack="Reconnaissance", user="u"),
        ev(4, 35, attack="Reconnaissance", host="a"),
    ]
    # host "a" reached stage 2, so t-004 links 25 min after t-002; user "u" did not, so t-003
    # (20 min after t-002) does not.
    assert groups(correlate(events, CONFIG, NOW)) == [["t-001", "t-002", "t-004"], ["t-003"]]


@pytest.mark.parametrize(
    ("attacks", "expected"),
    [
        (["Reconnaissance", "Reconnaissance", "Exploits"], "Exploits"),
        (["Exploits", "Generic", "Generic"], "Generic"),
        (["Exploits", "Generic"], "Exploits"),
        (["Backdoors", "DoS"], "DoS"),
        (["Reconnaissance", "NotInTable"], "Reconnaissance"),
        (["NotInTable"], "NotInTable"),
        ([None], None),
    ],
)
def test_incident_type_is_the_most_advanced_stage(attacks, expected):
    events = [ev(i, i, attack=a, host="a") for i, a in enumerate(attacks)]
    (incident,) = correlate(events, CONFIG, NOW).incidents
    assert incident.incident_type == expected


# --- configuration --------------------------------------------------------------------------


def test_config_file_loads_the_agreed_values():
    assert CONFIG.window == timedelta(minutes=15)
    assert CONFIG.escalated_window == timedelta(minutes=30)
    assert CONFIG.escalation_min_stage == 2
    assert [k.value for k in CONFIG.keys] == ["host", "ip_pair", "user"]
    assert not (CONFIG.denied_hosts or CONFIG.denied_ips or CONFIG.denied_users)
    assert CONFIG.stage("Backdoors") == 3 and CONFIG.stage(None) == 0


def test_escalated_window_must_not_be_shorter_than_the_window():
    with pytest.raises(ValueError, match="escalated_window"):
        CorrelationConfig(window=timedelta(minutes=15), escalated_window=timedelta(minutes=10))


def test_many_events_give_valid_incidents():
    rng = random.Random(7)
    events = []
    for n in range(3000):
        status = rng.choice(["flagged", "unflagged", "unflagged", "unlabelled"])
        events.append(
            ev(
                n,
                rng.randrange(0, 4 * 24 * 60),
                status,
                rng.choice(["Exploits", "Reconnaissance", "DoS", None])
                if status == "flagged"
                else None,
                host=f"h{rng.randrange(80)}",
                user=f"u{rng.randrange(60)}",
            )
        )
    result = correlate(events, CONFIG, NOW)
    linked = [link.event_id for inc in result.incidents for link in inc.events]
    assert len(linked) == len(set(linked))
    assert sorted(linked + list(result.unassigned_event_ids)) == sorted(e.event_id for e in events)


def test_demo_prints_the_fixture_incidents(capsys):
    from app.correlation.demo import main

    assert main([str(FIXTURES / "events.json")]) == 0
    out = capsys.readouterr().out
    assert "43 events -> 13 incidents (correlation-v0)" in out
    assert incident_id_for("fx-002") in out
