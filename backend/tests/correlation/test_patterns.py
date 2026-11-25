"""Count and order markers over an incident's flagged events (P5 of the competitor feature
study, F-A and F-D). Markers only: they never flag an event, infer a label or change a score (D2,
OD-04). Event time is the dataset clock.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import Event, EventRole
from app.correlation import correlate, load_config, load_risk_config, score_incidents
from app.correlation.patterns import (
    CountRule,
    PatternsConfig,
    SequenceRule,
    load_patterns_config,
    match_patterns,
)

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
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
CORRELATION = load_config()
PATTERNS = load_patterns_config()


def flagged(start: str, events=EVENTS) -> list[Event]:
    incident = next(i for i in INCIDENTS if i.events[0].event_id == start)
    ids = {link.event_id for link in incident.events if link.role == EventRole.FLAGGED}
    return [e for e in events if e.event_id in ids]


def found(events) -> dict[str, list[tuple[str, list[str]]]]:
    out: dict[str, list[tuple[str, list[str]]]] = {}
    for match in match_patterns(events, CORRELATION, PATTERNS):
        out.setdefault(match.pattern_id, []).append((match.key, match.event_ids))
    return out


def test_shipped_rules():
    assert PATTERNS.config_version == "patterns-v1"
    assert [r.pattern_id for r in PATTERNS.count_rules] == ["repeat-from-source"]
    assert [r.pattern_id for r in PATTERNS.sequence_rules] == [
        "recon-then-exploitation",
        "exploitation-then-installation",
    ]


def test_incident_a_shows_the_kill_chain_progression_on_web_01():
    # fx-002 Reconnaissance 09:00 -> fx-007 Exploits 09:10 -> fx-008 Backdoors 09:18, all web-01.
    matches = found(flagged("fx-002"))
    assert matches["recon-then-exploitation"][0] == ("web-01", ["fx-002", "fx-007"])
    assert matches["exploitation-then-installation"][0] == ("web-01", ["fx-007", "fx-008"])
    assert "repeat-from-source" not in matches  # at most two of a kind from one source


def test_order_matters():
    # ws-80: Exploits fx-038, Backdoors fx-039, then Reconnaissance later: no recon -> exploit.
    matches = found(flagged("fx-038"))
    assert matches["exploitation-then-installation"] == [("ws-80", ["fx-038", "fx-039"])]
    assert "recon-then-exploitation" not in matches


def test_sequence_needs_the_same_host_and_the_time_limit():
    events = flagged("fx-002")
    other_host = [
        e.model_copy(update={"host": "other"}) if e.event_id == "fx-007" else e for e in events
    ]
    assert ("web-01", ["fx-002", "fx-007"]) not in found(other_host).get(
        "recon-then-exploitation", []
    )
    late = [
        e.model_copy(update={"timestamp": e.timestamp + timedelta(minutes=61)})
        if e.event_id in {"fx-007", "fx-009", "fx-010"}
        else e
        for e in events
    ]
    assert "recon-then-exploitation" not in found(late)


def test_count_rule_on_the_same_source_and_attack_type_within_the_window():
    base = next(e for e in EVENTS if e.event_id == "fx-002")  # Reconnaissance from 203.0.113.10
    burst = [
        base.model_copy(
            update={"event_id": f"fx-b{n}", "timestamp": base.timestamp + timedelta(minutes=5 * n)}
        )
        for n in range(4)  # 0, 5, 10, 15 minutes
    ]
    [match] = found(burst)["repeat-from-source"]
    assert match == ("203.0.113.10 Reconnaissance", ["fx-b0", "fx-b1", "fx-b2", "fx-b3"])


def test_count_rule_boundary_is_inclusive_and_needs_the_minimum():
    base = next(e for e in EVENTS if e.event_id == "fx-002")
    spaced = [
        base.model_copy(
            update={
                "event_id": f"fx-s{n}",
                "timestamp": base.timestamp + timedelta(minutes=minutes),
            }
        )
        for n, minutes in enumerate([0, 8, 15])
    ]
    assert "repeat-from-source" in found(spaced)  # 15 minutes from first to third: inside
    wider = [
        e.model_copy(update={"timestamp": e.timestamp + timedelta(seconds=1)})
        if e.event_id == "fx-s2"
        else e
        for e in spaced
    ]
    assert "repeat-from-source" not in found(wider)
    assert "repeat-from-source" not in found(spaced[:2])


def test_context_and_unlabelled_events_are_never_passed_in_and_nothing_changes():
    events = flagged("fx-002")
    before = [e.model_dump() for e in events]
    match_patterns(events, CORRELATION, PATTERNS)
    assert [e.model_dump() for e in events] == before


def test_same_input_same_markers_in_any_order():
    events = flagged("fx-002")
    assert match_patterns(events, CORRELATION, PATTERNS) == match_patterns(
        list(reversed(events)), CORRELATION, PATTERNS
    )


@pytest.mark.parametrize(
    "rule",
    [
        lambda: CountRule("x", "t", min_events=1, within_minutes=5),
        lambda: CountRule("x", "t", min_events=3, within_minutes=0),
        lambda: SequenceRule("x", "t", first_stage=2, then_stage=2, within_minutes=5),
        lambda: SequenceRule("x", "t", first_stage=1, then_stage=2, within_minutes=-1),
    ],
)
def test_invalid_rules_are_refused(rule):
    with pytest.raises(ValueError):
        rule()


def test_duplicate_rule_ids_are_refused():
    rule = CountRule("x", "t", min_events=2, within_minutes=5)
    with pytest.raises(ValueError, match="twice"):
        PatternsConfig("v", (rule,), (SequenceRule("x", "t", 1, 2, 5),))
