"""Entity risk roll-up across incidents (P3 of the competitor feature study, F-C and F-H).

A read-only, deterministic view beside the incident score: per source-side entity, a
rank-weighted sum of its incidents' risk scores over a dataset-clock window, normalised to 0-100,
and the distinct ATT&CK tactics of its flagged events. It never changes an incident score or the
freeze gate. C3's real correlation and risk over fixtures/correlation/events.json.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import Event
from app.correlation import correlate, load_config, load_risk_config, score_incidents
from app.correlation.entity_risk import (
    EntityRiskConfig,
    entity_risk,
    load_entity_risk_config,
    rollup_score,
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
CONFIG = load_entity_risk_config()


def by_entity(report):
    return {item.entity: item for item in report.items}


def test_shipped_configuration_is_decision_d6():
    assert CONFIG.config_version == "entity-risk-v1"
    assert (CONFIG.window_hours, CONFIG.exponent, CONFIG.sample_size) == (24, 1.5, 10)
    assert (CONFIG.score_threshold, CONFIG.tactics_threshold) == (70, 3)


def test_rollup_formula():
    # zeta_10(1.5) = 1.99532...; a single 100 gives 50, ten 100s give 100.
    assert rollup_score([100], CONFIG) == 50
    assert rollup_score([100] * 10, CONFIG) == 100
    assert rollup_score([100] * 25, CONFIG) == 100  # only the top sample_size count
    assert rollup_score([32, 10, 10], CONFIG) == 19  # (32 + 10/2^1.5 + 10/3^1.5) / 1.99532
    assert rollup_score([10, 32, 10], CONFIG) == 19  # order of input does not matter
    assert rollup_score([], CONFIG) == 0


def test_fixture_entities_scores_and_order():
    report = entity_risk(INCIDENTS, EVENTS, CONFIG)
    items = by_entity(report)
    assert items["203.0.113.10"].score == 50
    assert items["ws-80"].score == 19
    assert items["ws-81"].score == 7
    assert "none" not in items  # an event with no IP, user or host names no entity
    scores = [(i.score, i.entity) for i in report.items]
    assert scores == sorted(scores, key=lambda s: (-s[0], s[1]))
    assert report.window_end == datetime(2026, 1, 15, 20, 20, tzinfo=UTC)
    assert report.window_start == report.window_end - timedelta(hours=24)


def test_each_entity_lists_its_incidents_and_levels():
    items = by_entity(entity_risk(INCIDENTS, EVENTS, CONFIG))
    ws80 = items["ws-80"]
    assert ws80.incident_count == 3
    assert [s for _, s in ws80.incidents] == [32, 10, 10]  # highest score first
    assert ws80.level == "low"
    assert items["203.0.113.10"].level == "medium"


def test_tactics_come_from_the_entitys_own_flagged_events():
    items = by_entity(entity_risk(INCIDENTS, EVENTS, CONFIG))
    # ws-80: Exploits (fx-038), Backdoors (fx-039), Reconnaissance (fx-042, fx-043) -> four.
    assert items["ws-80"].tactics == ["TA0001", "TA0003", "TA0011", "TA0043"]
    assert items["ws-80"].flags == ["tactic_threshold"]
    # 203.0.113.10 is the source of fx-002, fx-004 (Reconnaissance) and fx-007 (Exploits) only.
    assert items["203.0.113.10"].tactics == ["TA0001", "TA0043"]
    assert items["203.0.113.10"].flags == []


def test_score_threshold_flag():
    low = EntityRiskConfig("t", 24, 1.5, 10, score_threshold=40, tactics_threshold=9)
    items = by_entity(entity_risk(INCIDENTS, EVENTS, low))
    assert items["203.0.113.10"].flags == ["score_threshold"]


def test_incidents_outside_the_window_do_not_count():
    old = INCIDENTS[0].model_copy(
        update={
            "incident_id": "inc-old",
            "last_event_at": INCIDENTS[0].last_event_at - timedelta(hours=25),
        }
    )
    report = entity_risk([*INCIDENTS, old], EVENTS, CONFIG)
    assert by_entity(report)["203.0.113.10"].incident_count == 1


def test_unscored_incidents_are_skipped_and_nothing_is_changed():
    unscored = INCIDENTS[0].model_copy(update={"incident_id": "inc-new", "risk": None})
    before = [i.model_dump() for i in INCIDENTS]
    report = entity_risk([*INCIDENTS, unscored], EVENTS, CONFIG)
    assert by_entity(report)["203.0.113.10"].incident_count == 1
    assert [i.model_dump() for i in INCIDENTS] == before


def test_no_incidents_give_an_empty_report():
    report = entity_risk([], EVENTS, CONFIG)
    assert report.items == [] and report.window_end is None


def test_same_input_same_report():
    assert entity_risk(INCIDENTS, EVENTS, CONFIG) == entity_risk(
        list(reversed(INCIDENTS)), list(reversed(EVENTS)), CONFIG
    )


@pytest.mark.parametrize(
    "values",
    [(0, 1.5, 10, 70, 3), (24, 0, 10, 70, 3), (24, 1.5, 0, 70, 3), (24, 1.5, 10, 101, 3)],
)
def test_invalid_configuration_is_refused(values):
    with pytest.raises(ValueError):
        EntityRiskConfig("t", *values)
