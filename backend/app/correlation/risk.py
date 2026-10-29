"""Risk score v0 (C3, T2-09): incident -> deterministic 0 to 100 score, level and breakdown.

Method of the team decision of 29 Oct 2026 (docs/correlation-and-risk-design.md, section 9):

1. Each flagged event has a strength q = S * C * O * D. S is its severity (the source's own
   severity, else its kill-chain stage, else a default), C how far its dataset's label is
   trusted, O its outcome (success, failed or unknown), D a decay from the dataset clock W.
2. Events are grouped by (technique, source-side entity) and each group keeps only its
   strongest event, so repeated alerts and one source scanning many targets count once.
3. L = 1 - prod(1 - q_g) over the groups (noisy-OR).
4. I = the highest FIPS 199 impact among the incident's assets; an asset with no level counts
   as the worst case and sets the flag asset_unknown.
5. score = round half up (100 * L * I), level from the OD-05 thresholds.

Only flagged events count; context events never change the score. Nothing here reads the
clock or calls the LLM (OD-04): W and evaluated_at are passed in.
"""

import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fnmatch import fnmatchcase
from pathlib import Path

from app.contracts import (
    Event,
    EventRole,
    Incident,
    LabelStatus,
    RiskAssessment,
    RiskContributor,
    RiskFactor,
    RiskFlag,
)
from app.correlation.config import CorrelationConfig, load_config
from app.correlation.levels import DEFAULT_RISK_CONFIG_PATH, RiskThresholds, load_thresholds

TOP_CONTRIBUTORS = 3


@dataclass(frozen=True)
class RiskConfig:
    config_version: str = "risk-v0"
    thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    default_severity: float = 0.5
    stage_severity: dict[int, float] = field(default_factory=dict)
    source_severity: dict[str, float] = field(default_factory=dict)
    default_confidence: float = 1.0
    dataset_confidence: dict[str, float] = field(default_factory=dict)
    success_outcome: float = 1.0
    failed_outcome: float = 0.5
    unknown_outcome: float = 1.0
    success_values: frozenset[str] = frozenset()
    failed_values: frozenset[str] = frozenset()
    half_life: timedelta = timedelta(hours=24)
    strong_attack_types: frozenset[str] = frozenset()
    impact_levels: dict[str, float] = field(default_factory=dict)
    unknown_impact: float = 1.0
    assets: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.half_life <= timedelta(0):
            raise ValueError("half_life must be positive")
        values = [
            self.default_severity,
            *self.stage_severity.values(),
            *self.source_severity.values(),
            self.default_confidence,
            *self.dataset_confidence.values(),
            self.success_outcome,
            self.failed_outcome,
            self.unknown_outcome,
            *self.impact_levels.values(),
            self.unknown_impact,
        ]
        if any(not 0 <= v <= 1 for v in values):
            raise ValueError("severities, confidences, outcomes and impacts must be 0 to 1")
        for pattern, level in self.assets:
            if level not in self.impact_levels:
                raise ValueError(f"asset {pattern!r} has unknown level {level!r}")


def load_risk_config(
    path: Path = DEFAULT_RISK_CONFIG_PATH, assets_path: Path | None = None
) -> RiskConfig:
    """Read risk.toml; assets_path adds or overrides asset levels (the fixture's, for example)."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    severity, confidence, outcome = raw["severity"], raw["confidence"], raw["outcome"]
    assets = dict(raw.get("assets", {}))
    if assets_path is not None:
        assets.update(tomllib.loads(assets_path.read_text(encoding="utf-8")))
    return RiskConfig(
        config_version=raw["config_version"],
        thresholds=load_thresholds(path),
        default_severity=severity["default"],
        stage_severity={int(k): v for k, v in severity.get("stage", {}).items()},
        source_severity={k.lower(): v for k, v in severity.get("source_values", {}).items()},
        default_confidence=confidence["default"],
        dataset_confidence=dict(confidence.get("dataset", {})),
        success_outcome=outcome["success"],
        failed_outcome=outcome["failed"],
        unknown_outcome=outcome["unknown"],
        success_values=frozenset(v.lower() for v in outcome.get("success_values", [])),
        failed_values=frozenset(v.lower() for v in outcome.get("failed_values", [])),
        half_life=timedelta(hours=raw["decay"]["half_life_hours"]),
        strong_attack_types=frozenset(raw["decay"].get("strong_attack_types", [])),
        impact_levels=dict(raw["impact"]["levels"]),
        unknown_impact=raw["impact"]["unknown"],
        assets=tuple(sorted(assets.items())),
    )


@dataclass(frozen=True)
class EventStrength:
    event_id: str
    technique: str
    entity: str
    severity: float
    severity_source: str
    confidence: float
    outcome: float
    outcome_known: bool
    decay: float

    @property
    def strength(self) -> float:
        return self.severity * self.confidence * self.outcome * self.decay


def _text(event: Event, key: str) -> str | None:
    value = event.extra_fields.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


def entity_of(event: Event) -> str:
    """Source-side entity (team, 29 Oct): src IP, else user, else host, else none."""
    if event.src_ip is not None:
        return str(event.src_ip)
    if event.user is not None and event.user.strip():
        return event.user.strip().casefold()
    if event.host is not None and event.host.strip():
        return event.host.strip().lower()
    return "none"


def event_strength(
    event: Event, reference: datetime, config: RiskConfig, correlation: CorrelationConfig
) -> EventStrength:
    attack_type = event.label.attack_type
    source = _text(event, "severity")
    stage = correlation.stage(attack_type)
    if source is not None and source in config.source_severity:
        severity, severity_source = config.source_severity[source], f"source severity {source}"
    elif stage in config.stage_severity:
        severity, severity_source = config.stage_severity[stage], f"kill-chain stage {stage}"
    else:
        severity, severity_source = config.default_severity, "default"

    action = _text(event, "action")
    if action is not None and action in config.success_values:
        outcome, known = config.success_outcome, True
    elif action is not None and action in config.failed_values:
        outcome, known = config.failed_outcome, True
    else:
        outcome, known = config.unknown_outcome, False

    if attack_type in config.strong_attack_types:
        decay = 1.0
    else:
        age = max(reference - event.timestamp, timedelta(0))
        decay = 0.5 ** (age / config.half_life)

    return EventStrength(
        event_id=event.event_id,
        technique=attack_type or "unknown",
        entity=entity_of(event),
        severity=severity,
        severity_source=severity_source,
        confidence=config.dataset_confidence.get(
            event.provenance.dataset_id, config.default_confidence
        ),
        outcome=outcome,
        outcome_known=known,
        decay=decay,
    )


def asset_of(event: Event) -> str | None:
    """The affected asset: the host, else the destination IP (UNSW-NB15 flows have no host)."""
    if event.host is not None and event.host.strip():
        return event.host.strip().lower()
    if event.dst_ip is not None:
        return str(event.dst_ip)
    return None


def asset_impact(asset: str | None, config: RiskConfig) -> tuple[float, str | None]:
    """FIPS 199 impact of one asset and its level; (unknown_impact, None) when not rated."""
    if asset is not None:
        levels = [level for pattern, level in config.assets if fnmatchcase(asset, pattern)]
        if levels:
            level = max(levels, key=lambda name: (config.impact_levels[name], name))
            return config.impact_levels[level], level
    return config.unknown_impact, None


def _round_half_up(value: float) -> int:
    return int(Decimal(repr(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def score_incident(
    incident: Incident,
    events: Mapping[str, Event],
    reference: datetime,
    evaluated_at: datetime,
    config: RiskConfig,
    correlation: CorrelationConfig,
) -> RiskAssessment:
    """Score one incident. reference is the dataset clock W; evaluated_at is only stored."""
    flagged = sorted(
        (events[link.event_id] for link in incident.events if link.role == EventRole.FLAGGED),
        key=lambda e: (e.timestamp, e.event_id),
    )
    if not flagged:
        # The contract already requires a flagged event; this keeps the error explicit.
        raise ValueError(f"{incident.incident_id}: no flagged event to score")
    strengths = [event_strength(e, reference, config, correlation) for e in flagged]

    # Strongest event per (technique, entity); ties keep the earliest event.
    groups: dict[tuple[str, str], EventStrength] = {}
    for s in strengths:
        key = (s.technique, s.entity)
        if key not in groups or s.strength > groups[key].strength:
            groups[key] = s
    ranked = sorted(groups.values(), key=lambda s: (-s.strength, s.technique, s.entity))
    remaining = 1.0
    for s in sorted(groups.values(), key=lambda s: (s.technique, s.entity)):
        remaining *= 1 - s.strength
    likelihood = 1 - remaining

    rated = [(asset, *asset_impact(asset, config)) for asset in map(asset_of, flagged)]
    unknown = [asset for asset, _, level in rated if level is None]
    impact = max((value for _, value, _ in rated), default=config.unknown_impact)
    known = sorted({(value, asset) for asset, value, level in rated if level is not None})

    raw_score = 100 * likelihood * impact
    score = _round_half_up(raw_score)

    flags: list[RiskFlag] = []
    if unknown or not rated:
        flags.append(RiskFlag.ASSET_UNKNOWN)
    if any(not s.outcome_known for s in strengths):
        flags.append(RiskFlag.OUTCOME_UNKNOWN)
    if any(s.severity_source == "default" for s in strengths):
        flags.append(RiskFlag.SEVERITY_DEFAULT)

    top = ranked[0]
    likelihood_reason = (
        f"{len(groups)} evidence group{'s' if len(groups) != 1 else ''} from "
        f"{len(flagged)} flagged event{'s' if len(flagged) != 1 else ''}, combined by noisy-OR; "
        f"strongest: {top.technique} from {top.entity} ({_fmt(top.strength)})"
    )
    if unknown or not rated:
        impact_reason = (
            f"asset not rated ({', '.join(sorted({a or 'none' for a in unknown})) or 'none'}): "
            f"assumed {_fmt(config.unknown_impact)} (CVSS v4.0: Not Defined = High, worst case)"
        )
    else:
        value, asset = known[-1]
        level = asset_impact(asset, config)[1]
        impact_reason = f"highest asset {asset}: FIPS 199 {level} ({_fmt(value)})"

    return RiskAssessment(
        score=score,
        level=config.thresholds.level_for(score),
        factors=[
            RiskFactor(
                name="likelihood",
                value=likelihood,
                weight=1.0,
                contribution=100 * likelihood,
                reason=likelihood_reason,
            ),
            RiskFactor(
                name="impact",
                value=impact,
                weight=1.0,
                contribution=raw_score - 100 * likelihood,
                reason=impact_reason,
            ),
        ],
        config_version=config.config_version,
        computed_at=evaluated_at,
        likelihood=likelihood,
        impact=impact,
        flags=flags,
        top_contributors=[
            RiskContributor(
                technique=s.technique,
                entity=s.entity,
                strength=s.strength,
                event_id=s.event_id,
                reason=(
                    f"severity {_fmt(s.severity)} ({s.severity_source}) x confidence "
                    f"{_fmt(s.confidence)} x outcome {_fmt(s.outcome)}"
                    f"{'' if s.outcome_known else ' (unknown)'} x decay {_fmt(s.decay)}"
                ),
            )
            for s in ranked[:TOP_CONTRIBUTORS]
        ],
    )


def dataset_clock(events: Iterable[Event]) -> datetime:
    """W: the latest event time in the input (design note section 7.3)."""
    return max(e.timestamp for e in events)


def score_incidents(
    incidents: Iterable[Incident],
    events: Iterable[Event],
    evaluated_at: datetime,
    config: RiskConfig | None = None,
    correlation: CorrelationConfig | None = None,
) -> tuple[Incident, ...]:
    """Score every incident of a batch against the same dataset clock W."""
    config = config or load_risk_config()
    correlation = correlation or load_config()
    by_id = {e.event_id: e for e in events}
    incidents = tuple(incidents)
    if not incidents:
        return ()
    reference = dataset_clock(by_id.values())
    scored = []
    for incident in incidents:
        flagged = [link for link in incident.events if link.role == EventRole.FLAGGED]
        if any(by_id[link.event_id].label.status != LabelStatus.FLAGGED for link in flagged):
            raise ValueError(
                f"{incident.incident_id}: a flagged link points to a non-flagged event"
            )
        risk = score_incident(incident, by_id, reference, evaluated_at, config, correlation)
        # Re-validated, so a scored incident is checked by the contract like any other.
        scored.append(Incident.model_validate({**incident.model_dump(), "risk": risk.model_dump()}))
    return tuple(scored)
