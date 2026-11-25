"""Entity risk roll-up across incidents (P3, entity_risk.toml, decision D6).

Per source-side entity (risk.entity_of: source IP, else user, else host), over the incidents in a
dataset-clock window: a rank-weighted sum of the incidents' stored risk scores, normalised to
0-100, the distinct ATT&CK tactics of the entity's own flagged events (tactics.toml), and flags
when either reaches its threshold.

The idea comes from Elastic's entity risk score and Splunk's risk-based alerting (competitor
feature study, PR #51, sections F-C and F-H); this is a clean-room re-implementation. It is a
read-only view: it never changes an incident's score or level and never reaches the freeze gate.
Deterministic: the same incidents, events and configuration always give the same report.
"""

import tomllib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.contracts import Event, EventRole, Incident
from app.correlation.levels import level_for
from app.correlation.risk import entity_of
from app.correlation.tactics import TacticsConfig, load_tactics_config

DEFAULT_ENTITY_RISK_PATH = Path(__file__).with_name("entity_risk.toml")
NO_ENTITY = "none"


@dataclass(frozen=True)
class EntityRiskConfig:
    config_version: str
    window_hours: float
    exponent: float
    sample_size: int
    score_threshold: int
    tactics_threshold: int

    def __post_init__(self) -> None:
        if self.window_hours <= 0:
            raise ValueError("window_hours must be greater than 0")
        if self.exponent <= 0:
            raise ValueError("exponent must be greater than 0")
        if self.sample_size < 1:
            raise ValueError("sample_size must be at least 1")
        if not 0 <= self.score_threshold <= 100:
            raise ValueError("the score threshold must be in 0..100")
        if self.tactics_threshold < 1:
            raise ValueError("the tactics threshold must be at least 1")


def load_entity_risk_config(path: Path = DEFAULT_ENTITY_RISK_PATH) -> EntityRiskConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return EntityRiskConfig(
        config_version=raw["config_version"],
        window_hours=float(raw["window_hours"]),
        exponent=float(raw["score"]["exponent"]),
        sample_size=int(raw["score"]["sample_size"]),
        score_threshold=int(raw["thresholds"]["score"]),
        tactics_threshold=int(raw["thresholds"]["tactics"]),
    )


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


def rollup_score(scores: Iterable[int], config: EntityRiskConfig) -> int:
    """sum(s_i / i^p) over the top sample_size scores, over sum(1 / i^p), as 0..100."""
    top = sorted(scores, reverse=True)[: config.sample_size]
    weights = [k**-config.exponent for k in range(1, config.sample_size + 1)]
    value = sum(s * w for s, w in zip(top, weights, strict=False)) / sum(weights)
    return min(100, _round_half_up(value))


@dataclass(frozen=True)
class EntityRisk:
    entity: str
    score: int
    level: str
    incident_count: int
    incidents: list[tuple[str, int]]  # (incident_id, score), highest score first
    tactics: list[str]  # distinct tactic IDs, sorted
    flags: list[str]  # "score_threshold", "tactic_threshold"


@dataclass(frozen=True)
class EntityRiskReport:
    config_version: str
    tactics_config_version: str
    window_start: datetime | None
    window_end: datetime | None
    items: list[EntityRisk]


def entity_risk(
    incidents: Iterable[Incident],
    events: Iterable[Event],
    config: EntityRiskConfig,
    tactics: TacticsConfig | None = None,
) -> EntityRiskReport:
    """The roll-up of every source-side entity named by the scored incidents in the window."""
    tactics = tactics or load_tactics_config()
    by_id = {event.event_id: event for event in events}
    scored = [i for i in incidents if i.risk is not None]
    if not scored:
        return EntityRiskReport(config.config_version, tactics.config_version, None, None, [])
    window_end = max(i.last_event_at for i in scored)
    window_start = window_end - timedelta(hours=config.window_hours)

    entity_incidents: dict[str, dict[str, int]] = defaultdict(dict)
    entity_tactics: dict[str, set[str]] = defaultdict(set)
    for incident in scored:
        if incident.last_event_at < window_start:
            continue
        for link in incident.events:
            if link.role != EventRole.FLAGGED or link.event_id not in by_id:
                continue
            event = by_id[link.event_id]
            entity = entity_of(event)
            if entity == NO_ENTITY:
                continue
            entity_incidents[entity][incident.incident_id] = incident.risk.score
            found = tactics.tactics_for(event.label.attack_type)
            entity_tactics[entity].update(tactic_id for tactic_id, _ in found)

    items = []
    for entity, scores in entity_incidents.items():
        score = rollup_score(scores.values(), config)
        names = sorted(entity_tactics[entity])
        flags = []
        if score >= config.score_threshold:
            flags.append("score_threshold")
        if len(names) >= config.tactics_threshold:
            flags.append("tactic_threshold")
        items.append(
            EntityRisk(
                entity=entity,
                score=score,
                level=level_for(score).value,
                incident_count=len(scores),
                incidents=sorted(scores.items(), key=lambda pair: (-pair[1], pair[0])),
                tactics=names,
                flags=flags,
            )
        )
    items.sort(key=lambda item: (-item.score, item.entity))
    return EntityRiskReport(
        config.config_version, tactics.config_version, window_start, window_end, items
    )
