"""Risk levels (OD-05): the C3 -> C5 handoff for freeze precondition 2 (High)."""

import tomllib
from datetime import UTC, datetime

import pytest

from app.contracts import RiskAssessment, RiskFactor, RiskLevel
from app.correlation import RiskThresholds, check_level, is_high, level_for
from app.correlation.levels import DEFAULT_RISK_CONFIG_PATH, load_thresholds


def assessment(score: int, level: RiskLevel) -> RiskAssessment:
    return RiskAssessment(
        score=score,
        level=level,
        factors=[RiskFactor(name="severity", value=score / 100, weight=1.0, contribution=score)],
        config_version="risk-v0",
        computed_at=datetime(2026, 1, 15, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0, RiskLevel.LOW),
        (39, RiskLevel.LOW),
        (40, RiskLevel.MEDIUM),
        (69, RiskLevel.MEDIUM),
        (70, RiskLevel.HIGH),
        (100, RiskLevel.HIGH),
    ],
)
def test_level_boundaries_follow_od_05(score, level):
    assert level_for(score) == level


def test_every_score_has_exactly_one_level_and_levels_only_rise():
    levels = [level_for(s) for s in range(101)]
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
    assert [order.index(x) for x in levels] == sorted(order.index(x) for x in levels)
    assert levels.count(RiskLevel.LOW) == 40
    assert levels.count(RiskLevel.MEDIUM) == 30
    assert levels.count(RiskLevel.HIGH) == 31


@pytest.mark.parametrize("score", [-1, 101, 69.5, "70", None, True])
def test_level_rejects_anything_but_an_integer_score(score):
    with pytest.raises(ValueError):
        level_for(score)


def test_risk_toml_holds_the_ratified_thresholds():
    raw = tomllib.loads(DEFAULT_RISK_CONFIG_PATH.read_text(encoding="utf-8"))
    assert raw["config_version"] == "risk-v0"
    assert load_thresholds() == RiskThresholds(medium=40, high=70)


@pytest.mark.parametrize(("medium", "high"), [(0, 70), (70, 70), (80, 70), (40, 101)])
def test_thresholds_must_be_ordered_and_in_range(medium, high):
    with pytest.raises(ValueError):
        RiskThresholds(medium=medium, high=high)


def test_thresholds_are_configurable():
    stricter = RiskThresholds(medium=50, high=80)
    assert stricter.level_for(75) == RiskLevel.MEDIUM
    assert stricter.level_for(80) == RiskLevel.HIGH


def test_is_high_needs_a_scored_high_incident():
    assert is_high(assessment(70, RiskLevel.HIGH))
    assert not is_high(assessment(69, RiskLevel.MEDIUM))
    assert not is_high(None)  # not scored yet (Step 3 not run) is never a freeze


def test_check_level_accepts_a_consistent_assessment():
    for score in (0, 39, 40, 69, 70, 100):
        check_level(assessment(score, level_for(score)))


def test_check_level_rejects_a_level_that_does_not_match_the_score():
    # The contract accepts this; C3's code must not.
    with pytest.raises(ValueError, match="score 69 is medium"):
        check_level(assessment(69, RiskLevel.HIGH))
