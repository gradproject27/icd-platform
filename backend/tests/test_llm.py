import pytest

from app.llm.adapter import LLMAnalyzer, get_analyzer, uncited_event_ids
from app.llm.contracts import AnalysisReport, EvidencePackage, Finding
from app.llm.mock import MockAnalyzer

# Synthetic fixture, not dataset records.
EVIDENCE = EvidencePackage.model_validate(
    {
        "incident_id": "inc-001",
        "events": [
            {
                "event_id": "evt-1",
                "timestamp": "2026-01-01T10:00:00Z",
                "source": "auth.log",
                "summary": "5 failed SSH logins for root from 203.0.113.7",
            },
            {
                "event_id": "evt-2",
                "timestamp": "2026-01-01T10:01:00Z",
                "source": "auth.log",
                "summary": "Successful SSH login for root from 203.0.113.7",
            },
        ],
    }
)


def test_mock_output_is_schema_valid_after_json_round_trip():
    report = MockAnalyzer().analyze(EVIDENCE)
    restored = AnalysisReport.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.generated_by == "mock"
    assert all(f.statement.startswith("[MOCK]") for f in restored.findings)
    assert all("[SIMULATED]" in r for r in restored.recommendations)


def test_mock_cites_only_input_event_ids():
    report = MockAnalyzer().analyze(EVIDENCE)
    assert report.findings
    assert uncited_event_ids(report, EVIDENCE) == []


def test_uncited_event_ids_catches_invented_id():
    report = MockAnalyzer().analyze(EVIDENCE)
    report.findings.append(Finding(statement="invented", cited_event_ids=["evt-1", "evt-999"]))
    assert uncited_event_ids(report, EVIDENCE) == ["evt-999"]


def test_mock_is_deterministic():
    first = MockAnalyzer().analyze(EVIDENCE).model_dump_json()
    second = MockAnalyzer().analyze(EVIDENCE).model_dump_json()
    assert first == second


def test_mock_satisfies_protocol():
    assert isinstance(MockAnalyzer(), LLMAnalyzer)


def test_empty_evidence_gives_no_findings():
    report = MockAnalyzer().analyze(EvidencePackage(incident_id="inc-empty", events=[]))
    assert report.findings == []
    assert report.incident_id == "inc-empty"


def test_get_analyzer_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert isinstance(get_analyzer(), MockAnalyzer)


def test_get_analyzer_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "hpc")
    with pytest.raises(ValueError, match="hpc"):
        get_analyzer()
