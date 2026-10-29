"""Checks the C3 correlation fixtures (fixtures/correlation/) independently of the engine.

The expected incidents were written by hand. A reference below, which walks each key value's
flagged events in time order and merges groups by repeated set merging (no union-find),
recomputes them from the rules in docs/correlation-and-risk-design.md, so a wrong
hand-written answer fails here. tests/correlation/ checks the engine against the same file.
"""

import fnmatch
import ipaddress
import json
import tomllib
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from app.contracts import Event, LabelStatus

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "correlation"
RAW_EVENTS = json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURES / "expected-incidents.json").read_text(encoding="utf-8"))
EVENTS = [Event.model_validate(e) for e in RAW_EVENTS]
BY_ID = {e.event_id: e for e in EVENTS}

CONFIG = tomllib.loads(
    (ROOT / "backend" / "app" / "correlation" / "correlation.toml").read_text(encoding="utf-8")
)
WINDOW = timedelta(minutes=15)
ESCALATED_WINDOW = timedelta(minutes=30)
ESCALATION_MIN_STAGE = 2
STAGES = CONFIG["kill_chain"]["attack_types"]
KEYS = ("host", "ip_pair", "user")
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


def stage(e: Event) -> int:
    return STAGES.get(e.label.attack_type, 0) if e.label.attack_type else 0


def reference_incidents() -> list[dict]:
    """Reference for sections 5 to 8 of the design note with the 28 Oct answers (no union-find)."""
    flagged = sorted((e for e in EVENTS if e.label.status == LabelStatus.FLAGGED), key=order)
    context = [e for e in EVENTS if e.label.status != LabelStatus.FLAGGED]

    # Per key value, walk its flagged events in time order. Two consecutive ones are linked when
    # the gap is within the window in force: 30 min while the chain has reached stage 2+.
    chains: dict[tuple[str, object], list[Event]] = defaultdict(list)
    for e in flagged:
        for k, v in key_values(e).items():
            chains[(k, v)].append(e)
    pairs: list[tuple[Event, Event]] = []
    link_keys: dict[str, set[str]] = defaultdict(set)
    earlier_keys: dict[str, set[str]] = defaultdict(set)
    for (k, _), chain in chains.items():
        escalated = stage(chain[0]) >= ESCALATION_MIN_STAGE
        for prev, e in zip(chain, chain[1:], strict=False):
            window = ESCALATED_WINDOW if escalated else WINDOW
            if e.timestamp - prev.timestamp <= window:
                pairs.append((prev, e))
                link_keys[e.event_id].add(k)
                earlier_keys[prev.event_id].add(k)
            else:
                escalated = False
            escalated = escalated or stage(e) >= ESCALATION_MIN_STAGE

    # Connected components of the linked pairs, by repeated merging.
    groups = [{e.event_id} for e in flagged]
    for a, b in pairs:
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
        links = [
            {
                "event_id": e.event_id,
                "link_keys": []
                if n == 0
                else [k for k in KEYS if k in (link_keys[e.event_id] or earlier_keys[e.event_id])],
            }
            for n, e in enumerate(members)
        ]
        types = Counter(e.label.attack_type for e in members if e.label.attack_type)
        incident_type = None
        if types:
            top = max(STAGES.get(t, 0) for t in types)
            incident_type = min(
                (t for t in types if STAGES.get(t, 0) == top), key=lambda t: (-types[t], t)
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


# Risk score (T2-09). An independent reference for the team's method of 29 Oct 2026 (design
# note section 9), read straight from risk.toml, checks the hand-kept expected-risk.json.

RISK = tomllib.loads(
    (ROOT / "backend" / "app" / "correlation" / "risk.toml").read_text(encoding="utf-8")
)
ASSETS = tomllib.loads((FIXTURES / "assets.toml").read_text(encoding="utf-8"))
EXPECTED_RISK = json.loads((FIXTURES / "expected-risk.json").read_text(encoding="utf-8"))


def reference_risk(flagged_ids: list[str]) -> dict:
    clock = max(e.timestamp for e in EVENTS)
    half_life = timedelta(hours=RISK["decay"]["half_life_hours"])
    best: dict[tuple[str, str], tuple[float, str]] = {}
    for event_id in sorted(flagged_ids, key=lambda i: order(BY_ID[i])):
        e = BY_ID[event_id]
        s = RISK["severity"]["stage"].get(str(stage(e)), RISK["severity"]["default"])
        strong = e.label.attack_type in RISK["decay"]["strong_attack_types"]
        d = 1.0 if strong else 0.5 ** ((clock - e.timestamp) / half_life)
        q = s * RISK["confidence"]["default"] * RISK["outcome"]["unknown"] * d
        if e.src_ip is not None:
            entity = str(e.src_ip)
        elif e.user and e.user.strip():
            entity = e.user.strip().casefold()
        else:
            entity = e.host.strip().lower() if e.host and e.host.strip() else "none"
        key = (e.label.attack_type or "unknown", entity)
        if key not in best or q > best[key][0]:
            best[key] = (q, event_id)
    likelihood = 1.0
    for q, _ in best.values():
        likelihood *= 1 - q
    likelihood = 1 - likelihood
    impacts = []
    for event_id in flagged_ids:
        e = BY_ID[event_id]
        if e.host and e.host.strip():
            asset = e.host.strip().lower()
        else:
            asset = str(e.dst_ip) if e.dst_ip else None
        levels = [v for p, v in ASSETS.items() if asset and fnmatch.fnmatchcase(asset, p)]
        impacts.append(
            max(RISK["impact"]["levels"][v] for v in levels)
            if levels
            else RISK["impact"]["unknown"]
        )
    impact = max(impacts)
    score = int(Decimal(repr(100 * likelihood * impact)).quantize(Decimal(1), ROUND_HALF_UP))
    thresholds = RISK["thresholds"]
    level = (
        "high"
        if score >= thresholds["high"]
        else "medium"
        if score >= thresholds["medium"]
        else "low"
    )
    top = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[:3]
    return {
        "score": score,
        "level": level,
        "likelihood": round(likelihood, 4),
        "impact": impact,
        "top_event_ids": [event_id for _, (_, event_id) in top],
    }


def test_expected_risk_covers_every_incident():
    assert EXPECTED_RISK["risk_config_version"] == RISK["config_version"]
    assert sorted(r["start_event_id"] for r in EXPECTED_RISK["incidents"]) == sorted(
        i["start_event_id"] for i in EXPECTED["incidents"]
    )


@pytest.mark.parametrize("index", range(len(EXPECTED_RISK["incidents"])))
def test_hand_kept_risk_matches_the_method(index):
    expected = EXPECTED_RISK["incidents"][index]
    incident = next(
        i for i in EXPECTED["incidents"] if i["start_event_id"] == expected["start_event_id"]
    )
    got = reference_risk([link["event_id"] for link in incident["flagged"]])
    assert got == {
        "score": expected["score"],
        "level": expected["level"],
        "likelihood": expected["likelihood"],
        "impact": expected["impact"],
        "top_event_ids": [c["event_id"] for c in expected["top_contributors"]],
    }, expected["label"]
