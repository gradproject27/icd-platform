import pytest

from app.contracts import AnalysisReport, EvidencePackage, Finding, FindingCategory, SequenceStep
from app.llm.adapter import LLMAnalyzer, get_analyzer, uncited_event_ids
from app.llm.mock import MockAnalyzer

# Synthetic fixture, not dataset records.
EVIDENCE = EvidencePackage.model_validate(
    {
        "package_id": "pkg-001",
        "incident_id": "inc-001",
        "created_at": "2026-01-01T10:05:00Z",
        "incident": {
            "first_event_at": "2026-01-01T10:00:00Z",
            "last_event_at": "2026-01-01T10:01:00Z",
            "flagged_event_count": 2,
            "context_event_count": 0,
            "host_count": 1,
        },
        "events": [
            {
                "event_id": "evt-1",
                "timestamp": "2026-01-01T10:00:00Z",
                "event_type": "ssh_auth_failure",
                "role": "flagged",
                "label_status": "flagged",
                "host": "host-01",
                "src_ip": "ip-01",
                "user": "user-01",
                "summary": "5 failed SSH logins for user-01 from ip-01",
                "source": "auth.log",
            },
            {
                "event_id": "evt-2",
                "timestamp": "2026-01-01T10:01:00Z",
                "event_type": "ssh_auth_success",
                "role": "flagged",
                "label_status": "flagged",
                "host": "host-01",
                "src_ip": "ip-01",
                "user": "user-01",
                "summary": "Successful SSH login for user-01 from ip-01",
                "source": "auth.log",
            },
        ],
        "total_event_count": 2,
        "truncated": False,
    }
)


def test_mock_output_is_schema_valid_after_json_round_trip():
    report = MockAnalyzer().analyze(EVIDENCE)
    restored = AnalysisReport.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.generated_by == "mock"
    assert restored.generated_at == EVIDENCE.created_at
    assert restored.evidence_package_id == EVIDENCE.package_id
    assert restored.summary.startswith("[MOCK]")
    assert all(f.statement.startswith("[MOCK]") for f in restored.findings)
    assert all("[SIMULATED]" in r for r in restored.recommendations)


def test_mock_cites_only_input_event_ids():
    report = MockAnalyzer().analyze(EVIDENCE)
    assert report.findings
    assert uncited_event_ids(report, EVIDENCE) == []


def test_uncited_event_ids_catches_invented_id():
    report = MockAnalyzer().analyze(EVIDENCE)
    invented = Finding(
        statement="invented",
        category=FindingCategory.EVIDENCE_SUPPORTED,
        cited_event_ids=["evt-1", "evt-999"],
    )
    report = report.model_copy(update={"findings": [*report.findings, invented]})
    assert uncited_event_ids(report, EVIDENCE) == ["evt-999"]


def test_uncited_event_ids_checks_sequence_steps():
    report = MockAnalyzer().analyze(EVIDENCE)
    step = SequenceStep(order=1, description="invented", cited_event_ids=["evt-2", "evt-998"])
    report = report.model_copy(update={"sequence": [step]})
    assert uncited_event_ids(report, EVIDENCE) == ["evt-998"]


def test_mock_is_deterministic():
    first = MockAnalyzer().analyze(EVIDENCE).model_dump_json()
    second = MockAnalyzer().analyze(EVIDENCE).model_dump_json()
    assert first == second


def test_mock_satisfies_protocol():
    assert isinstance(MockAnalyzer(), LLMAnalyzer)


def test_empty_evidence_gives_no_findings():
    empty = EvidencePackage.model_validate(
        {
            **EVIDENCE.model_dump(),
            "incident_id": "inc-empty",
            "events": [],
            "total_event_count": 0,
            "truncated": False,
        }
    )
    report = MockAnalyzer().analyze(empty)
    assert report.findings == []
    assert report.incident_id == "inc-empty"


def test_get_analyzer_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert isinstance(get_analyzer(), MockAnalyzer)


def test_get_analyzer_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "hpc")
    with pytest.raises(ValueError, match="hpc"):
        get_analyzer()
