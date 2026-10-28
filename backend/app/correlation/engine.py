"""Correlation engine v0 (C3, T2-08): flagged events -> incidents, deterministic.

Follows docs/correlation-and-risk-design.md, sections 3 to 8, with the team answers of
28 Oct 2026 (Q1 to Q9):

1. Flagged events are sorted by (timestamp, event_id) and grouped with union-find. A flagged
   event is linked to the previous flagged event with the same key value when the gap is within
   the window in force for that value: `window` (15 min, inclusive), or `escalated_window`
   (30 min) while the value's current chain has reached kill-chain stage
   `escalation_min_stage` or later (adaptive memory). The memory ends when the chain breaks.
2. Unflagged and unlabelled events are attached as context to the group of the nearest flagged
   event that shares a key value within the base window; ties go to the earliest group. Context
   events never merge groups and never use the escalated window.
3. Each group becomes one Incident in state new. Its type is the attack type of the most
   advanced kill-chain stage reached by its flagged events.

The function never reads the clock: `now` is passed in, so the same events, configuration and
`now` always give the same incidents (AS-04). The risk score is left null (T2-09).
"""

import hashlib
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.contracts import (
    Event,
    EventRole,
    Incident,
    IncidentEventLink,
    LabelStatus,
    LinkKey,
)
from app.correlation.config import CorrelationConfig
from app.correlation.keys import KeyValue, key_values, ordered


@dataclass(frozen=True)
class CorrelationResult:
    incidents: tuple[Incident, ...]
    unassigned_event_ids: tuple[str, ...]
    config_version: str


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, i: int) -> int:
        root = i
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[i] != root:
            self.parent[i], i = root, self.parent[i]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _order(event: Event) -> tuple[datetime, str]:
    return (event.timestamp, event.event_id)


def incident_id_for(start_event_id: str) -> str:
    """Stable ID from the flagged event that started the incident (decision D3)."""
    return "inc-" + hashlib.sha256(start_event_id.encode("utf-8")).hexdigest()[:16]


def incident_type_for(flagged: list[Event], config: CorrelationConfig) -> str | None:
    """Attack type of the most advanced kill-chain stage (Q9); ties by frequency, then name."""
    types = [e.label.attack_type for e in flagged if e.label.attack_type is not None]
    if not types:
        return None
    top = max(config.stage(t) for t in types)
    counts = Counter(t for t in types if config.stage(t) == top)
    return min(counts, key=lambda t: (-counts[t], t))


def _group_flagged(
    flagged: list[Event], config: CorrelationConfig
) -> tuple[_UnionFind, list[set[LinkKey]]]:
    uf = _UnionFind(len(flagged))
    link_keys: list[set[LinkKey]] = [set() for _ in flagged]
    earlier_keys: list[set[LinkKey]] = [set() for _ in flagged]
    last: dict[KeyValue, int] = {}
    escalated: dict[KeyValue, bool] = {}
    for i, event in enumerate(flagged):
        stage = config.stage(event.label.attack_type)
        for value in key_values(event, config):
            prev = last.get(value)
            if prev is not None:
                window = config.escalated_window if escalated.get(value) else config.window
                if event.timestamp - flagged[prev].timestamp <= window:
                    uf.union(i, prev)
                    link_keys[i].add(value[0])
                    earlier_keys[prev].add(value[0])
                else:
                    escalated[value] = False  # the chain broke: the memory ends
            last[value] = i
            if stage >= config.escalation_min_stage:
                escalated[value] = True
    # An event that started a chain which a later event merged into an older group has no keys
    # as the later event; it takes the keys that later events linked to it by (contract: only
    # the starting event may have no link_keys).
    return uf, [later or earlier for later, earlier in zip(link_keys, earlier_keys, strict=True)]


def correlate(events: list[Event], config: CorrelationConfig, now: datetime) -> CorrelationResult:
    """Group one batch of events into incidents (single batch; cross-upload updates: Week 3)."""
    ids = [e.event_id for e in events]
    if len(ids) != len(set(ids)):
        raise ValueError("event IDs must be unique")

    flagged = sorted((e for e in events if e.label.status == LabelStatus.FLAGGED), key=_order)
    context = sorted((e for e in events if e.label.status != LabelStatus.FLAGGED), key=_order)
    uf, flagged_keys = _group_flagged(flagged, config)

    members: dict[int, list[int]] = defaultdict(list)
    for i in range(len(flagged)):
        members[uf.find(i)].append(i)
    groups = sorted(members.values(), key=lambda g: g[0])  # by first flagged event in order
    group_of = {i: gi for gi, g in enumerate(groups) for i in g}

    # Context attachment: nearest flagged event sharing a key value within the base window.
    by_value: dict[KeyValue, list[int]] = defaultdict(list)
    for i, event in enumerate(flagged):
        for value in key_values(event, config):
            by_value[value].append(i)
    times_by_value = {v: [flagged[i].timestamp for i in idx] for v, idx in by_value.items()}
    attached: dict[int, list[tuple[Event, set[LinkKey]]]] = defaultdict(list)
    unassigned: list[str] = []
    for c in context:
        best: tuple[timedelta, int, int] | None = None
        for value in key_values(c, config):
            candidates = by_value.get(value, [])
            pos = bisect_left(times_by_value.get(value, []), c.timestamp)
            for j in (pos - 1, pos):
                if 0 <= j < len(candidates):
                    i = candidates[j]
                    gap = abs(c.timestamp - flagged[i].timestamp)
                    if gap <= config.window:
                        option = (gap, group_of[i], i)
                        best = option if best is None or option < best else best
        if best is None:
            unassigned.append(c.event_id)
            continue
        f_values = set(key_values(flagged[best[2]], config))
        shared = {k for k, v in key_values(c, config) if (k, v) in f_values}
        attached[best[1]].append((c, shared))

    incidents = []
    for gi, group in enumerate(groups):
        group_flagged = [flagged[i] for i in group]
        links = [
            IncidentEventLink(
                event_id=flagged[i].event_id,
                role=EventRole.FLAGGED,
                link_keys=[] if n == 0 else ordered(flagged_keys[i]),
                linked_at=now,
            )
            for n, i in enumerate(group)
        ]
        links += [
            IncidentEventLink(
                event_id=c.event_id, role=EventRole.CONTEXT, link_keys=ordered(keys), linked_at=now
            )
            for c, keys in attached[gi]
        ]
        times = [e.timestamp for e in group_flagged] + [c.timestamp for c, _ in attached[gi]]
        incidents.append(
            Incident(
                incident_id=incident_id_for(group_flagged[0].event_id),
                incident_type=incident_type_for(group_flagged, config),
                created_at=now,
                updated_at=now,
                first_event_at=min(times),
                last_event_at=max(times),
                events=links,
            )
        )
    return CorrelationResult(
        incidents=tuple(incidents),
        unassigned_event_ids=tuple(sorted(unassigned)),
        config_version=config.config_version,
    )
