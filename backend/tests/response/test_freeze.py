"""Freeze preconditions (FR-43, NFR-SF-06, AS-09): one test per failing condition, plus the pass."""

import pytest

from app.contracts import AnalysisStatus, Incident, RiskLevel
from app.response import NoFreezeReason, Targets, check_freeze, find_targets, report_valid

R = NoFreezeReason


def check(incident, events, config, *, window_open=False, targets=None):
    targets = targets or find_targets(incident, events, config)
    return check_freeze(incident, targets, window_open=window_open, config=config)


def test_high_risk_high_confidence_valid_report_freezes(incident_a, events, config, analysed):
    result = check(analysed(incident_a, 0.9), events, config)
    assert result.freeze and result.reasons == ()


def test_confidence_exactly_at_the_threshold_freezes(incident_a, events, config, analysed):
    assert check(analysed(incident_a, 0.75), events, config).freeze


def test_confidence_just_below_the_threshold_does_not_freeze(incident_a, events, config, analysed):
    result = check(analysed(incident_a, 0.7499), events, config)
    assert result.reasons == (R.CONFIDENCE_BELOW_THRESHOLD,)


def test_failed_report_never_freezes(incident_a, events, config, analysed):
    result = check(analysed(incident_a, None), events, config)
    assert not result.freeze
    assert result.reasons == (R.ANALYSIS_NOT_VALID, R.CONFIDENCE_BELOW_THRESHOLD)


def test_analysis_not_started_never_freezes(incident_a, events, config):
    assert incident_a.analysis_status == AnalysisStatus.NOT_STARTED
    result = check(incident_a, events, config)
    assert R.ANALYSIS_NOT_VALID in result.reasons


@pytest.mark.parametrize("start", ["fx-005", "fx-021"])  # F is Medium, C1 is Low
def test_not_high_never_freezes_even_with_full_confidence(
    start, events, config, analysed, fixture_incident
):
    incident = analysed(fixture_incident(start), 1.0)
    assert incident.risk.level != RiskLevel.HIGH
    assert check(incident, events, config).reasons[0] == R.RISK_NOT_HIGH


def test_not_scored_yet_never_freezes(incident_a, events, config, analysed):
    unscored = Incident.model_validate(analysed(incident_a, 1.0).model_dump() | {"risk": None})
    assert check(unscored, events, config).reasons == (R.RISK_NOT_HIGH,)


def test_second_window_is_refused(incident_a, events, config, analysed):
    result = check(analysed(incident_a, 0.9), events, config, window_open=True)
    assert result.reasons == (R.WINDOW_ALREADY_OPEN,)


def test_no_target_host_does_not_freeze(incident_a, events, config, analysed):
    no_host = Targets(host=None, source_ip="203.0.113.10", account=None)
    result = check(analysed(incident_a, 0.9), events, config, targets=no_host)
    assert result.reasons == (R.NO_TARGET_HOST,)


def test_every_reason_is_reported_together(events, config, fixture_incident):
    incident = fixture_incident("fx-005")  # Medium, no host, not analysed
    result = check(incident, events, config, window_open=True)
    assert set(result.reasons) == set(R)
    assert result.as_details()["freeze"] is False


def test_report_valid_needs_succeeded_and_a_report(incident_a, analysed):
    assert report_valid(analysed(incident_a, 0.1))
    assert not report_valid(analysed(incident_a, None))
    assert not report_valid(incident_a)
