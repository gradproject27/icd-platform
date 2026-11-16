"""Size cap (W3-D13) and the split record (contracts 1.2), decisions of 16 Nov 2026."""

import json
import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import Event, EventRole, IncidentSplit, SplitReason
from app.correlation import correlate, incident_id_for, load_config
from app.correlation.engine import split_points

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(e)
    for e in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
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


PAIR = {"src_ip": "203.0.113.5", "dst_ip": "198.51.100.7"}


def at(*seconds):
    return [T0 + timedelta(seconds=s) for s in seconds]


def capped(cap):
    return replace(CONFIG, max_incident_events=cap)


def chain(minutes, **extra):
    """Flagged events on one IP pair, one per entry of minutes (t-001, t-002, ...)."""
    return [ev(n, m, attack="Exploits", **PAIR, **extra) for n, m in enumerate(minutes, 1)]


# --- split_points ---------------------------------------------------------------------------


def test_fits_no_cut():
    assert split_points(at(0, 1, 2), [1, 1, 1], 3) == []


def test_cut_at_the_largest_gap():
    assert split_points(at(0, 1, 9, 10), [1, 1, 1, 1], 3) == [2]


def test_tie_goes_to_the_earliest_gap():
    assert split_points(at(0, 5, 10, 15), [1, 1, 1, 1], 3) == [1]


def test_cuts_again_until_every_part_fits():
    # Largest gap first (before position 3), then the left part at its own largest gap.
    assert split_points(at(0, 2, 3, 20, 21), [1, 1, 1, 1, 1], 2) == [1, 3]


def test_context_counts_toward_the_cap():
    # Each flagged event brings 2 links, so 2 flagged events (4 links) exceed a cap of 3.
    assert split_points(at(0, 1), [2, 2], 3) == [1]


def test_one_flagged_event_over_the_cap_is_kept_whole():
    assert split_points(at(0), [9], 3) == []
    assert split_points(at(0, 1), [9, 1], 3) == [1]


@pytest.mark.parametrize("seed", range(30))
def test_every_part_fits_or_cannot_be_cut(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 60)
    times = at(*sorted(rng.choice([0, 1, 2, 5, 30]) * k for k in range(n)))
    sizes = [rng.randint(1, 4) for _ in range(n)]
    cap = rng.randint(2, 25)
    bounds = [0, *split_points(times, sizes, cap), n]
    for a, b in zip(bounds, bounds[1:], strict=False):
        assert a < b
        assert sum(sizes[a:b]) <= cap or b - a == 1


# --- correlate with a cap -------------------------------------------------------------------


def test_the_shared_fixture_is_under_the_production_cap():
    config = load_config()
    assert config.max_incident_events == 500
    assert config.config_version == "correlation-v1"
    result = correlate(EVENTS, config, NOW)
    assert all(inc.split is None for inc in result.incidents)
    assert {inc.correlation_config_version for inc in result.incidents} == {"correlation-v1"}


def test_a_group_over_the_cap_becomes_parts():
    events = chain([0, 1, 2, 10, 11, 12])  # one gap of 8 minutes, inside the 15 min window
    assert len(correlate(events, CONFIG, NOW).incidents) == 1
    result = correlate(events, capped(3), NOW)
    assert groups(result) == [["t-001", "t-002", "t-003"], ["t-004", "t-005", "t-006"]]
    first, second = result.incidents
    assert first.incident_id == incident_id_for("t-001")
    assert second.incident_id == incident_id_for("t-004")
    assert first.split == IncidentSplit(
        reason=SplitReason.SIZE_CAP, cap=3, group_id=first.incident_id, part=1, parts=2
    )
    assert second.split == IncidentSplit(
        reason=SplitReason.SIZE_CAP,
        cap=3,
        group_id=first.incident_id,
        part=2,
        parts=2,
        gap_seconds=480.0,
    )
    assert second.first_event_at == T0 + timedelta(minutes=10)
    assert first.last_event_at == T0 + timedelta(minutes=2)


def test_each_part_starts_its_own_incident():
    result = correlate(chain([0, 1, 2, 10, 11, 12]), capped(3), NOW)
    for inc in result.incidents:
        assert inc.events[0].link_keys == []
        assert all(link.link_keys for link in inc.events[1:])


def test_context_stays_with_its_flagged_event():
    events = chain([0, 1, 10, 11]) + [
        ev(20, 0.5, status="unflagged", **PAIR),
        ev(21, 10.5, status="unflagged", **PAIR),
    ]
    result = correlate(events, capped(3), NOW)
    roles = [[(link.event_id, link.role) for link in inc.events] for inc in result.incidents]
    assert roles == [
        [("t-001", EventRole.FLAGGED), ("t-002", EventRole.FLAGGED), ("t-020", EventRole.CONTEXT)],
        [("t-003", EventRole.FLAGGED), ("t-004", EventRole.FLAGGED), ("t-021", EventRole.CONTEXT)],
    ]


def test_no_event_is_lost_or_duplicated_by_a_split():
    rng = random.Random(4)
    minutes = sorted(rng.uniform(0, 600) for _ in range(300))
    minutes = [m for i, m in enumerate(minutes) if i == 0 or m - minutes[i - 1] <= 14]
    events = chain(minutes) + [
        ev(500 + n, m + 0.1, status="unflagged", **PAIR) for n, m in enumerate(minutes[::7])
    ]
    whole = correlate(events, CONFIG, NOW)
    parts = correlate(events, capped(40), NOW)
    ids = lambda r: sorted(link.event_id for i in r.incidents for link in i.events)  # noqa: E731
    assert ids(parts) == ids(whole)
    assert parts.unassigned_event_ids == whole.unassigned_event_ids
    assert all(len(inc.events) <= 40 for inc in parts.incidents)
    assert len(parts.incidents) > 1
    numbers = [inc.split.part for inc in parts.incidents]
    assert numbers == list(range(1, len(parts.incidents) + 1))
    assert {inc.split.group_id for inc in parts.incidents} == {whole.incidents[0].incident_id}


def test_parts_get_their_own_incident_type():
    events = [ev(1, 0, attack="Reconnaissance", **PAIR), ev(2, 1, attack="Reconnaissance", **PAIR)]
    events += [ev(3, 10, attack="Backdoors", **PAIR), ev(4, 11, attack="Exploits", **PAIR)]
    result = correlate(events, capped(2), NOW)
    assert [inc.incident_type for inc in result.incidents] == ["Reconnaissance", "Backdoors"]


def test_split_is_deterministic_and_order_free():
    events = chain([0, 1, 2, 10, 11, 12, 20, 21])
    shuffled = list(events)
    random.Random(1).shuffle(shuffled)
    dump = lambda r: [i.model_dump_json() for i in r.incidents]  # noqa: E731
    assert dump(correlate(events, capped(3), NOW)) == dump(correlate(shuffled, capped(3), NOW))


def test_scope_goes_into_every_id_and_the_group_id():
    result = correlate(chain([0, 1, 2, 10, 11, 12]), capped(3), NOW, scope="upl-1")
    assert [i.incident_id for i in result.incidents] == [
        incident_id_for("t-001", "upl-1"),
        incident_id_for("t-004", "upl-1"),
    ]
    assert {i.split.group_id for i in result.incidents} == {incident_id_for("t-001", "upl-1")}
    # Same IDs as C1's earlier upload scoping (incident storage D4).
    assert incident_id_for("t-001", "upl-1") == incident_id_for("upl-1/t-001")


def test_cap_below_two_is_refused():
    with pytest.raises(ValueError, match="at least 2"):
        capped(1)


# --- the contract ---------------------------------------------------------------------------


def split(**fields):
    base = {"reason": "size_cap", "cap": 500, "group_id": "inc-1", "part": 2, "parts": 3}
    return IncidentSplit.model_validate({**base, "gap_seconds": 60.0, **fields})


def test_split_contract_accepts_a_valid_part():
    assert split().part == 2
    assert split(part=1, gap_seconds=None).gap_seconds is None


@pytest.mark.parametrize(
    "fields",
    [
        {"part": 4},
        {"parts": 1, "part": 1, "gap_seconds": None},
        {"part": 1},
        {"gap_seconds": None},
        {"gap_seconds": -1},
        {"reason": "too_big"},
        {"cap": 0},
    ],
)
def test_split_contract_refuses(fields):
    with pytest.raises(ValidationError):
        split(**fields)


def test_old_incidents_without_the_new_fields_still_validate():
    from app.contracts import Incident

    data = correlate(EVENTS, CONFIG, NOW).incidents[0].model_dump(mode="json")
    del data["split"], data["correlation_config_version"]
    assert Incident.model_validate(data).split is None


def test_time_zone_of_parts_is_utc():
    result = correlate(chain([0, 1, 2, 10]), capped(2), NOW)
    assert all(i.first_event_at.tzinfo == UTC for i in result.incidents)
    assert result.incidents[0].created_at == NOW == datetime(2026, 1, 16, tzinfo=UTC)
