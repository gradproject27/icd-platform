"""Shared fixture incidents for the response engine tests: C3's real correlation and risk score
over fixtures/correlation/events.json, then an analysis outcome set by the test."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts import AnalysisStatus, Event, Incident, IncidentStatus
from app.correlation import correlate, load_config, load_risk_config, score_incidents
from app.response import load_response_config

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "correlation"
EVENTS = [
    Event.model_validate(e)
    for e in json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))
]
NOW = datetime(2026, 1, 15, 20, 20, tzinfo=UTC)
_SCORED = score_incidents(
    correlate(EVENTS, load_config(), NOW).incidents,
    EVENTS,
    evaluated_at=NOW,
    config=load_risk_config(assets_path=FIXTURES / "assets.toml"),
)
_BY_START = {inc.events[0].event_id: inc for inc in _SCORED}
for _inc in _SCORED:
    for _link in _inc.events:
        if not _link.link_keys:
            _BY_START[_link.event_id] = _inc


def _fixture_incident(start_event_id: str) -> Incident:
    """The scored incident that fixture event `start_event_id` started (A is fx-002)."""
    return _BY_START[start_event_id]


def _analysed(
    incident: Incident,
    confidence: float | None = 0.9,
    status: IncidentStatus = IncidentStatus.UNDER_ANALYSIS,
) -> Incident:
    """The incident with a succeeded analysis and this confidence; None means it failed."""
    if confidence is None:
        update = {"analysis_status": AnalysisStatus.FAILED, "analysis_attempts": 1}
    else:
        update = {
            "analysis_status": AnalysisStatus.SUCCEEDED,
            "analysis_attempts": 1,
            "latest_report_id": f"rep-{incident.incident_id}",
            "confidence": confidence,
        }
    return Incident.model_validate(incident.model_dump() | update | {"status": status})


@pytest.fixture
def config():
    return load_response_config()


@pytest.fixture
def events():
    return EVENTS


@pytest.fixture
def incident_a():
    """Fixture incident A: score 100, High, Backdoors, hosts web-01, db-01, file-01."""
    return _fixture_incident("fx-002")


@pytest.fixture
def fixture_incident():
    """fixture_incident(start_event_id) -> the scored fixture incident."""
    return _fixture_incident


@pytest.fixture
def analysed():
    """analysed(incident, confidence=0.9, status=...) -> incident with that analysis outcome."""
    return _analysed
