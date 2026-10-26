"""Checks the C3 correlation fixtures (fixtures/correlation/) before any engine exists.

The expected incidents were written by hand. A brute-force reference below, which
compares every pair of events, recomputes them from the rules in
docs/correlation-and-risk-design.md, so a wrong hand-written answer fails here.
"""

import ipaddress
import json
from collections import Counter
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

import pytest

from app.contracts import Event, LabelStatus

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "correlation"
RAW_EVENTS = json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURES / "expected-incidents.json").read_text(encoding="utf-8"))
EVENTS = [Event.model_validate(e) for e in RAW_EVENTS]
BY_ID = {e.event_id: e for e in EVENTS}

WINDOW = timedelta(minutes=15)
KEYS = ("host", "ip_pair", "user")
# Provisional UNSW-NB15 severity table (decision D2); only used for incident-type ties here.
SEVERITY = {
    "Reconnaissance": 0.3,
    "Fuzzers": 0.3,
    "Analysis": 0.4,
    "Generic": 0.5,
    "DoS": 0.6,
    "Exploits": 0.8,
    "Shellcode": 0.8,
    "Backdoors": 0.9,
    "Worms": 0.9,
}
DEFAULT_SEVERITY = 0.5
PLACEHOLDER_NETS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
]


def key_values(e: Event) -> dict[str, object]:
    values: dict[str, object] = {}
    if e.host is not None:
        values["host"] = e.host.strip().lower()
    if e.src_ip is not None and e.dst_ip is not None:
        values["ip_pair"] = frozenset({str(e.src_ip), str(e.dst_ip)})
    if e.user is not None:
        values["user"] = e.user.strip().casefold()
    return values


def shared_keys(a: Event, b: Event) -> list[str]:
    ka, kb = key_values(a), key_values(b)
    return [k for k in KEYS if k in ka and k in kb and ka[k] == kb[k]]


def related(a: Event, b: Event) -> bool:
    return bool(shared_keys(a, b)) and abs(a.timestamp - b.timestamp) <= WINDOW


def order(e: Event):
    return (e.timestamp, e.event_id)


def reference_incidents() -> list[dict]:
    """All-pairs reference for sections 5 to 8 of the design note (no union-find)."""
    flagged = sorted((e for e in EVENTS if e.label.status == LabelStatus.FLAGGED), key=order)
    context = [e for e in EVENTS if e.label.status != LabelStatus.FLAGGED]

    # Connected components of the "directly related" relation, by repeated merging.
    groups = [{e.event_id} for e in flagged]
    for a, b in combinations(flagged, 2):
        if related(a, b):
            ga = next(g for g in groups if a.event_id in g)
            gb = next(g for g in groups if b.event_id in g)
            if ga is not gb:
                ga |= gb
                groups.remove(gb)

    def first(g):
        return min((BY_ID[i] for i in g), key=order)

    groups.sort(key=lambda g: order(first(g)))
    attached: dict[int, list[tuple[str, list[str]]]] = {i: [] for i in range(len(groups))}
    for c in context:
        candidates = [
            (abs(c.timestamp - f.timestamp), order(first(g)), order(f), gi, f)
            for gi, g in enumerate(groups)
            for f in (BY_ID[i] for i in g)
            if related(c, f)
        ]
        if candidates:
            *_, gi, f = min(candidates, key=lambda t: t[:3])
            attached[gi].append((c.event_id, shared_keys(c, f)))

    result = []
    for gi, g in enumerate(groups):
        members = sorted((BY_ID[i] for i in g), key=order)
        links = []
        for e in members:
            earlier = [p for p in flagged if order(p) < order(e)]
            keys = {k for p in earlier if related(p, e) for k in shared_keys(p, e)}
            links.append({"event_id": e.event_id, "link_keys": [k for k in KEYS if k in keys]})
        types = Counter(e.label.attack_type for e in members if e.label.attack_type)
        incident_type = None
        if types:
            incident_type = min(
                types, key=lambda t: (-types[t], -SEVERITY.get(t, DEFAULT_SEVERITY), t)
            )
        ctx = sorted(attached[gi], key=lambda t: order(BY_ID[t[0]]))
        times = [e.timestamp for e in members] + [BY_ID[i].timestamp for i, _ in ctx]
        privileged = [e.privileged_user for e in members if e.privileged_user is not None]
        result.append(
            {
                "start_event_id": members[0].event_id,
                "flagged": links,
                "context": [{"event_id": i, "link_keys": k} for i, k in ctx],
                "first_event_at": min(times),
                "last_event_at": max(times),
                "incident_type": incident_type,
                "hosts": sorted({key_values(e)["host"] for e in members if e.host}),
                "attack_types": sorted(types),
                "privileged": any(privileged) if privileged else None,
            }
        )
    return result


def test_every_fixture_event_is_a_valid_event():
    assert len(EVENTS) == len(RAW_EVENTS)
    assert 30 <= len(EVENTS) <= 50


def test_event_ids_are_unique():
    assert len(BY_ID) == len(EVENTS)


def test_fixture_uses_placeholders_only():
    for e in EVENTS:
        for ip in (e.src_ip, e.dst_ip):
            if ip is not None:
                assert any(ip in net for net in PLACEHOLDER_NETS), (e.event_id, ip)


def test_fixture_covers_every_label_status():
    statuses = {e.label.status for e in EVENTS}
    assert statuses == set(LabelStatus)


def test_expected_file_covers_every_event_exactly_once():
    ids = [link["event_id"] for inc in EXPECTED["incidents"] for link in inc["flagged"]]
    ids += [link["event_id"] for inc in EXPECTED["incidents"] for link in inc["context"]]
    ids += [row["event_id"] for row in EXPECTED["not_in_any_incident"]]
    assert sorted(ids) == sorted(BY_ID)


def test_expected_roles_match_labels():
    for inc in EXPECTED["incidents"]:
        assert inc["flagged"], inc["label"]
        for link in inc["flagged"]:
            assert BY_ID[link["event_id"]].label.status == LabelStatus.FLAGGED
        for link in inc["context"]:
            assert BY_ID[link["event_id"]].label.status != LabelStatus.FLAGGED
    for row in EXPECTED["not_in_any_incident"]:
        assert BY_ID[row["event_id"]].label.status != LabelStatus.FLAGGED


def _comparable(inc: dict) -> dict:
    out = {k: v for k, v in inc.items() if k not in ("label", "case")}
    for k in ("first_event_at", "last_event_at"):
        out[k] = datetime.fromisoformat(inc[k])
    return out


@pytest.mark.parametrize("index", range(len(EXPECTED["incidents"])))
def test_hand_written_incident_matches_the_rules(index):
    expected = EXPECTED["incidents"][index]
    reference = reference_incidents()
    assert len(reference) == len(EXPECTED["incidents"])
    match = next(r for r in reference if r["start_event_id"] == expected["start_event_id"])
    assert _comparable(expected) == match, expected["label"]
