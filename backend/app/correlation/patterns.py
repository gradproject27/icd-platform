"""Count and order markers over an incident's flagged events (P5, patterns.toml).

Ideas from Wazuh's frequency rules and Elastic's EQL sequences (competitor feature study, PR #51,
sections F-A and F-D), re-implemented clean-room on ICD's rules: only events the dataset already
flagged are read, nothing is flagged or labelled, and no score changes (Rule 1, D2; OD-04). Time
is the dataset clock. Deterministic: the same events always give the same markers.
"""

import tomllib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.contracts import Event
from app.correlation.config import CorrelationConfig
from app.correlation.risk import entity_of

DEFAULT_PATTERNS_PATH = Path(__file__).with_name("patterns.toml")
MAX_EVENTS = 10  # cited events per marker
NO_ENTITY = "none"


@dataclass(frozen=True)
class CountRule:
    pattern_id: str
    title: str
    min_events: int
    within_minutes: float

    def __post_init__(self) -> None:
        if self.min_events < 2:
            raise ValueError(f"{self.pattern_id}: min_events must be at least 2")
        if self.within_minutes <= 0:
            raise ValueError(f"{self.pattern_id}: within_minutes must be greater than 0")


@dataclass(frozen=True)
class SequenceRule:
    pattern_id: str
    title: str
    first_stage: int
    then_stage: int
    within_minutes: float

    def __post_init__(self) -> None:
        if not 0 < self.first_stage < self.then_stage:
            raise ValueError(f"{self.pattern_id}: first_stage must come before then_stage")
        if self.within_minutes <= 0:
            raise ValueError(f"{self.pattern_id}: within_minutes must be greater than 0")


@dataclass(frozen=True)
class PatternsConfig:
    config_version: str
    count_rules: tuple[CountRule, ...]
    sequence_rules: tuple[SequenceRule, ...]

    def __post_init__(self) -> None:
        ids = [r.pattern_id for r in (*self.count_rules, *self.sequence_rules)]
        if len(ids) != len(set(ids)):
            raise ValueError("a pattern id is used twice")


def load_patterns_config(path: Path = DEFAULT_PATTERNS_PATH) -> PatternsConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return PatternsConfig(
        config_version=raw["config_version"],
        count_rules=tuple(
            CountRule(r["id"], r["title"], int(r["min_events"]), float(r["within_minutes"]))
            for r in raw.get("count", [])
        ),
        sequence_rules=tuple(
            SequenceRule(
                r["id"],
                r["title"],
                int(r["first_stage"]),
                int(r["then_stage"]),
                float(r["within_minutes"]),
            )
            for r in raw.get("sequence", [])
        ),
    )


@dataclass(frozen=True)
class PatternMatch:
    pattern_id: str
    title: str
    key: str  # what the events share: "source attack-type" or the host
    event_ids: list[str]
    first_seen: datetime


def _order(event: Event) -> tuple[datetime, str]:
    return (event.timestamp, event.event_id)


def _count(rule: CountRule, events: list[Event]) -> list[PatternMatch]:
    groups: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in events:
        entity, attack_type = entity_of(event), event.label.attack_type
        if entity != NO_ENTITY and attack_type:
            groups[(entity, attack_type)].append(event)
    window = timedelta(minutes=rule.within_minutes)
    matches = []
    for (entity, attack_type), group in groups.items():
        for i, first in enumerate(group):
            inside = [e for e in group[i:] if e.timestamp - first.timestamp <= window]
            if len(inside) >= rule.min_events:
                matches.append(
                    PatternMatch(
                        rule.pattern_id,
                        rule.title,
                        f"{entity} {attack_type}",
                        [e.event_id for e in inside[:MAX_EVENTS]],
                        first.timestamp,
                    )
                )
                break  # the earliest window per source and attack type
    return matches


def _sequence(
    rule: SequenceRule, events: list[Event], correlation: CorrelationConfig
) -> list[PatternMatch]:
    hosts: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        if event.host:
            hosts[event.host].append(event)
    window = timedelta(minutes=rule.within_minutes)
    matches = []
    for host, group in hosts.items():
        stage = [correlation.stage(e.label.attack_type) for e in group]
        for i, first in enumerate(group):
            if stage[i] != rule.first_stage:
                continue
            then = next(
                (
                    e
                    for j, e in enumerate(group[i + 1 :], start=i + 1)
                    if stage[j] == rule.then_stage and e.timestamp - first.timestamp <= window
                ),
                None,
            )
            if then is not None:
                matches.append(
                    PatternMatch(
                        rule.pattern_id,
                        rule.title,
                        host,
                        [first.event_id, then.event_id],
                        first.timestamp,
                    )
                )
                break  # the earliest pair per host
    return matches


def match_patterns(
    flagged: Iterable[Event], correlation: CorrelationConfig, config: PatternsConfig
) -> list[PatternMatch]:
    """Markers over an incident's flagged events, earliest first. Reads only; changes nothing."""
    events = sorted(flagged, key=_order)
    matches = [m for rule in config.count_rules for m in _count(rule, events)]
    matches += [m for rule in config.sequence_rules for m in _sequence(rule, events, correlation)]
    return sorted(matches, key=lambda m: (m.first_seen, m.pattern_id, m.key))
