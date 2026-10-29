"""Risk score v0 (T2-09): the team's method of 29 Oct 2026, its goals and its edge cases."""

import json
import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import Event, Incident, RiskFlag, RiskLevel
from app.correlation import (
    check_level,
    correlate,
    incident_id_for,
    load_config,
    load_risk_config,
    score_incident,
    score_incidents,
)
from app.correlation.risk import RiskConfig, _round_half_up, entity_of, event_strength

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(e)
    for e in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
EXPECTED_RISK = json.loads((FIXTURES / "expected-risk.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 1, 16, tzinfo=UTC)
CORRELATION = load_config()
RISK = load_risk_config(assets_path=FIXTURES / "assets.toml")
T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def ev(n, minutes=0, status="flagged", attack=None, dataset="test", extra=None, **fields):
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
                "dataset_id": dataset,
                "source_file": "test.json",
                "record_ref": str(n),
                "source_format": "json",
            },
            "extra_fields": extra or {},
            **fields,
        }
    )


def incident_of(events):
    """One incident holding all the flagged events given, linked as flagged (no context)."""
    flagged = [e for e in events if e.label.status == "flagged"]
    return Incident.model_validate(
        {
            "incident_id": incident_id_for(flagged[0].event_id),
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "first_event_at": min(e.timestamp for e in events).isoformat(),
            "last_event_at": max(e.timestamp for e in events).isoformat(),
            "events": [
                {
                    "event_id": e.event_id,
                    "role": "flagged" if e.label.status == "flagged" else "context",
                    "link_keys": [] if i == 0 else ["host"],
                    "linked_at": NOW.isoformat(),
                }
                for i, e in enumerate(events)
            ],
        }
    )


def risk_of(events, config=RISK, reference=None):
    reference = reference or max(e.timestamp for e in events)
    by_id = {e.event_id: e for e in events}
    return score_incident(incident_of(events), by_id, reference, NOW, config, CORRELATION)


def scored_fixture(events=EVENTS):
    result = correlate(events, CORRELATION, NOW)
    return score_incidents(result.incidents, events, NOW, RISK, CORRELATION)


# --- the shared fixture ---------------------------------------------------------------------


def test_fixture_scores_match_the_expected_file():
    scored = {i.incident_id: i.risk for i in scored_fixture()}
    assert len(scored) == len(EXPECTED_RISK["incidents"])
    for exp in EXPECTED_RISK["incidents"]:
        risk = scored[incident_id_for(exp["start_event_id"])]
        got = {
            "score": risk.score,
            "level": risk.level.value,
            "likelihood": round(risk.likelihood, 4),
            "impact": risk.impact,
            "flags": [f.value for f in risk.flags],
            "top_contributors": [
                {
                    "technique": c.technique,
                    "entity": c.entity,
                    "event_id": c.event_id,
                    "strength": round(c.strength, 4),
                }
                for c in risk.top_contributors
            ],
        }
        expected = {k: v for k, v in exp.items() if k not in ("label", "start_event_id")}
        assert got == expected, exp["label"]


def test_only_attack_a_is_high_on_the_fixture():
    levels = {i.incident_id: i.risk.level for i in scored_fixture()}
    high = [k for k, v in levels.items() if v == RiskLevel.HIGH]
    assert high == [incident_id_for("fx-002")]


def test_every_scored_incident_is_consistent_and_explained():
    for incident in scored_fixture():
        risk = incident.risk
        check_level(risk)
        assert risk.config_version == "risk-v0" and risk.computed_at == NOW
        assert [f.name for f in risk.factors] == ["likelihood", "impact"]
        assert all(f.reason for f in risk.factors)
        assert 1 <= len(risk.top_contributors) <= 3 and all(c.reason for c in risk.top_contributors)
        # The factor contributions add up to the unrounded score.
        total = sum(f.contribution for f in risk.factors)
        assert abs(total - 100 * risk.likelihood * risk.impact) < 1e-9
        assert risk.score == _round_half_up(total)


# --- determinism (AS-04) ------------------------------------------------------------------------


def test_same_input_same_scores():
    first = [i.model_dump() for i in scored_fixture()]
    assert first == [i.model_dump() for i in scored_fixture()]


@pytest.mark.parametrize("seed", range(10))
def test_input_order_does_not_change_scores(seed):
    shuffled = EVENTS[:]
    random.Random(seed).shuffle(shuffled)
    expected = {i.incident_id: i.risk for i in scored_fixture()}
    assert {i.incident_id: i.risk for i in scored_fixture(shuffled)} == expected


def test_evaluated_at_is_stored_but_never_changes_the_score():
    result = correlate(EVENTS, CORRELATION, NOW)
    a = score_incidents(result.incidents, EVENTS, NOW, RISK, CORRELATION)
    b = score_incidents(result.incidents, EVENTS, NOW + timedelta(days=400), RISK, CORRELATION)
    assert [i.risk.score for i in a] == [i.risk.score for i in b]
    assert {i.risk.computed_at for i in b} == {NOW + timedelta(days=400)}


def test_no_incidents_gives_no_scores():
    assert score_incidents((), EVENTS, NOW, RISK, CORRELATION) == ()


# --- the method's goals ---------------------------------------------------------------------


@pytest.mark.parametrize("targets", [5, 20, 50])
def test_a_scan_of_many_targets_scores_like_one_target(targets):
    def scan(n):
        return [
            ev(i, 0, attack="Reconnaissance", src_ip="203.0.113.9", dst_ip=f"10.0.0.{i + 1}")
            for i in range(n)
        ]

    assert risk_of(scan(targets)).score == risk_of(scan(1)).score


def test_repeating_the_same_alert_does_not_raise_the_score():
    once = [ev(0, 0, attack="Exploits", src_ip="203.0.113.9", host="web-01")]
    hundred = [ev(i, 0, attack="Exploits", src_ip="203.0.113.9", host="web-01") for i in range(100)]
    assert risk_of(hundred).score == risk_of(once).score


def test_with_a_fixed_clock_more_evidence_never_lowers_the_score():
    rng = random.Random(7)
    types = ["Reconnaissance", "Exploits", "Backdoors", "DoS", None]
    events, reference = [], T0 + timedelta(hours=2)
    previous = 0
    for i in range(40):
        events.append(
            ev(
                i,
                rng.randint(0, 120),
                attack=rng.choice(types),
                src_ip=f"203.0.113.{rng.randint(1, 4)}",
            )
        )
        score = risk_of(events, reference=reference).score
        assert score >= previous
        previous = score


def test_context_events_never_change_the_score():
    flagged = [
        ev(0, 0, attack="Exploits", host="web-01"),
        ev(1, 5, attack="Backdoors", host="web-01"),
    ]
    context = [
        ev(2, 3, status="unflagged", host="web-01"),
        ev(3, 4, status="unlabelled", host="web-01"),
    ]
    assert risk_of(flagged + context, reference=T0) == risk_of(flagged, reference=T0)


def test_a_backdoor_outscores_a_wide_reconnaissance_scan():
    backdoor = [ev(0, 0, attack="Backdoors", src_ip="203.0.113.9", host="web-01")]
    scan = [
        ev(i, 0, attack="Reconnaissance", src_ip="203.0.113.9", host=f"ws-{i}") for i in range(50)
    ]
    assert risk_of(backdoor).score > risk_of(scan).score


# --- the factors ----------------------------------------------------------------------------


def test_severity_prefers_the_source_value_then_the_stage_then_the_default():
    source = event_strength(
        ev(0, attack="Reconnaissance", extra={"severity": " Critical "}), T0, RISK, CORRELATION
    )
    staged = event_strength(ev(1, attack="Exploits"), T0, RISK, CORRELATION)
    unknown = event_strength(
        ev(2, attack="NotAType", extra={"severity": "weird"}), T0, RISK, CORRELATION
    )
    assert (source.severity, staged.severity, unknown.severity) == (1.0, 0.6, 0.5)
    assert RiskFlag.SEVERITY_DEFAULT in risk_of([ev(3, attack=None)]).flags


def test_the_spelling_variant_backdoor_has_the_backdoors_stage():
    assert CORRELATION.stage("Backdoor") == CORRELATION.stage("Backdoors") == 3


def test_confidence_is_the_trust_in_the_datasets_label():
    assert (
        event_strength(
            ev(0, attack="Exploits", dataset="precinct6"), T0, RISK, CORRELATION
        ).confidence
        == 0.8
    )
    assert (
        event_strength(
            ev(1, attack="Exploits", dataset="unsw-nb15"), T0, RISK, CORRELATION
        ).confidence
        == 1.0
    )


def test_outcome_failed_halves_success_keeps_unknown_keeps_and_flags():
    failed = risk_of([ev(0, attack="Exploits", host="web-01", extra={"action": "Blocked"})])
    success = risk_of([ev(0, attack="Exploits", host="web-01", extra={"action": "allowed"})])
    unknown = risk_of([ev(0, attack="Exploits", host="web-01")])
    assert failed.likelihood == pytest.approx(success.likelihood / 2)
    assert success.likelihood == unknown.likelihood
    assert (
        RiskFlag.OUTCOME_UNKNOWN in unknown.flags and RiskFlag.OUTCOME_UNKNOWN not in success.flags
    )
    assert failed.score > 0  # a blocked attack never vanishes


def test_decay_halves_after_one_half_life_but_never_for_a_compromise():
    reference = T0 + timedelta(hours=24)
    old = event_strength(ev(0, 0, attack="Exploits"), reference, RISK, CORRELATION)
    backdoor = event_strength(ev(1, 0, attack="Backdoors"), reference, RISK, CORRELATION)
    future = event_strength(ev(2, 60, attack="Exploits"), T0, RISK, CORRELATION)
    assert old.decay == pytest.approx(0.5)
    assert backdoor.decay == 1.0
    assert future.decay == 1.0  # an event after the clock is not boosted


def test_entity_is_the_source_side():
    assert entity_of(ev(0, src_ip="203.0.113.9", user="Bob", host="WS-1")) == "203.0.113.9"
    assert entity_of(ev(1, user=" Bob ", host="WS-1")) == "bob"
    assert entity_of(ev(2, host=" WS-1 ")) == "ws-1"
    assert entity_of(ev(3)) == "none"


def test_impact_takes_the_highest_asset_and_unknown_is_the_worst_case():
    known = risk_of([ev(0, attack="Exploits", host="ws-9"), ev(1, attack="Exploits", host="db-01")])
    unknown = risk_of([ev(0, attack="Exploits", host="srv-77")])
    no_asset = risk_of([ev(0, attack="Exploits")])
    assert known.impact == 1.0 and RiskFlag.ASSET_UNKNOWN not in known.flags
    assert unknown.impact == 1.0 and RiskFlag.ASSET_UNKNOWN in unknown.flags
    assert RiskFlag.ASSET_UNKNOWN in no_asset.flags
    assert risk_of([ev(0, attack="Exploits", host="ws-9")]).impact == 0.33


def test_without_a_host_the_destination_ip_is_the_asset():
    config = replace(RISK, assets=(("10.0.0.5", "low"),))
    risk = risk_of([ev(0, attack="Exploits", src_ip="203.0.113.9", dst_ip="10.0.0.5")], config)
    assert risk.impact == 0.33 and RiskFlag.ASSET_UNKNOWN not in risk.flags


def test_an_unknown_asset_never_scores_below_a_known_one():
    for host in ("ws-1", "web-01", "db-01"):
        known = risk_of([ev(0, attack="Exploits", host=host)])
        unknown = risk_of([ev(0, attack="Exploits", host="unrated-host")])
        assert unknown.score >= known.score


def test_round_half_up():
    assert [_round_half_up(v) for v in (69.5, 69.49, 0.5, 39.5)] == [70, 69, 1, 40]


def test_production_config_has_no_assets_so_every_real_asset_is_unknown():
    production = load_risk_config()
    assert production.assets == ()
    assert (
        RiskFlag.ASSET_UNKNOWN
        in risk_of([ev(0, attack="Exploits", host="db-01")], production).flags
    )


@pytest.mark.parametrize(
    "change",
    [
        {"half_life": timedelta(0)},
        {"default_severity": 1.5},
        {"unknown_impact": -0.1},
        {"assets": (("db-*", "extreme"),)},
    ],
)
def test_invalid_configuration_is_refused(change):
    with pytest.raises(ValueError):
        replace(RiskConfig(impact_levels={"low": 0.33}), **change)


def test_a_flagged_link_to_a_non_flagged_event_is_refused():
    events = [ev(0, attack="Exploits", host="web-01"), ev(1, 1, status="unflagged", host="web-01")]
    incident = incident_of(events).model_copy()
    bad = Incident.model_validate(
        {
            **incident.model_dump(),
            "events": [{**link.model_dump(), "role": "flagged"} for link in incident.events],
        }
    )
    with pytest.raises(ValueError, match="non-flagged"):
        score_incidents([bad], events, NOW, RISK, CORRELATION)


# --- sensitivity: a 20% change to each group of values (recorded in design note section 9.2) -


def _clip(value):
    return min(1.0, max(0.0, value))


def _scaled(factor):
    return {
        "severity": replace(
            RISK,
            stage_severity={k: _clip(v * factor) for k, v in RISK.stage_severity.items()},
            default_severity=_clip(RISK.default_severity * factor),
        ),
        "half_life": replace(RISK, half_life=RISK.half_life * factor),
        "impact_levels": replace(
            RISK, impact_levels={k: _clip(v * factor) for k, v in RISK.impact_levels.items()}
        ),
        "unknown_impact": replace(RISK, unknown_impact=_clip(RISK.unknown_impact * factor)),
    }


@pytest.mark.parametrize(
    ("factor", "changed"),
    [
        (0.8, {"severity": 1, "half_life": 0, "impact_levels": 0, "unknown_impact": 1}),
        (1.2, {"severity": 0, "half_life": 0, "impact_levels": 0, "unknown_impact": 0}),
    ],
)
def test_a_20_percent_change_moves_at_most_one_fixture_incident_to_another_level(factor, changed):
    result = correlate(EVENTS, CORRELATION, NOW)
    base = {i.incident_id: i.risk.level for i in scored_fixture()}
    for name, config in _scaled(factor).items():
        levels = {
            i.incident_id: i.risk.level
            for i in score_incidents(result.incidents, EVENTS, NOW, config, CORRELATION)
        }
        assert sum(levels[k] != base[k] for k in base) == changed[name], name
        assert levels[incident_id_for("fx-002")] == RiskLevel.HIGH, name


def test_an_incident_without_flagged_events_is_refused_explicitly():
    events = [ev(0, attack="Exploits", host="web-01"), ev(1, 1, status="unflagged", host="web-01")]
    incident = incident_of(events)
    only_context = incident.model_construct(
        **{**dict(incident), "events": [link for link in incident.events if link.role == "context"]}
    )
    by_id = {e.event_id: e for e in events}
    with pytest.raises(ValueError, match="no flagged event"):
        score_incident(only_context, by_id, T0, NOW, RISK, CORRELATION)
