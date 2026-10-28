import pytest

from app.analysis import (
    LlmOutput,
    check_output,
    compute_confidence,
    evidence_completeness,
    to_report,
)
from app.analysis.confidence import GROUNDING_FLOOR
from app.contracts import EvidencePackage, FindingCategory
from tests.analysis.conftest import META


def _report(output: LlmOutput, evidence, confidence=0.5):
    return to_report(
        output,
        evidence,
        report_id=META.report_id,
        generated_at=META.generated_at,
        generated_by=META.generated_by,
        model_id=META.model_id,
        prompt_version=META.prompt_version,
        confidence=confidence,
    )


def test_mapping_keeps_every_section(evidence, good_output):
    output = LlmOutput.model_validate(good_output)
    report = _report(output, evidence)
    assert report.summary == output.summary.text
    assert report.attack_type == "credential_compromise_with_exfiltration"
    assert [s.order for s in report.sequence] == [1, 2, 3, 4, 5]
    assert report.sequence[0].cited_event_ids == output.sequence[0].cited_event_ids
    assert [f.category for f in report.findings] == [c.category for c in output.findings]
    assert report.weaknesses is None
    assert report.impact == output.impact.text
    assert "Why:" in report.recommendations[0]
    assert "Less disruptive option:" in report.recommendations[0]
    assert "Less disruptive option:" not in report.recommendations[1]
    assert "would be settled by" in report.uncertainty
    assert "Limitations:" in report.uncertainty
    assert report.model_self_rating == 0.8


def test_not_determined_sections_stay_null(evidence, good_output):
    for key in ("attack_type", "sequence", "impact", "risk_justification"):
        good_output[key] = None
    report = _report(LlmOutput.model_validate(good_output), evidence)
    assert report.attack_type is None
    assert report.sequence is None
    assert report.impact is None
    assert report.risk_justification is None


def test_categories_match_the_contract():
    schema = LlmOutput.model_json_schema()
    assert schema["$defs"]["FindingCategory"]["enum"] == [c.value for c in FindingCategory]


def test_completeness_counts_key_fields_on_flagged_events(evidence):
    # 11 flagged events x 3 key fields; E-010 has no src_ip, E-011 has no user.
    assert evidence_completeness(evidence) == pytest.approx(31 / 33)


def _thin_package() -> EvidencePackage:
    return EvidencePackage.model_validate(
        {
            "package_id": "pkg-thin",
            "incident_id": "inc-thin",
            "created_at": "2026-03-02T10:00:00Z",
            "incident": {
                "risk_score": 75,
                "risk_level": "high",
                "first_event_at": "2026-03-02T09:00:00Z",
                "last_event_at": "2026-03-02T09:00:00Z",
                "flagged_event_count": 1,
                "context_event_count": 0,
                "host_count": 0,
            },
            "events": [
                {
                    "event_id": "E-001",
                    "timestamp": "2026-03-02T09:00:00Z",
                    "event_type": "alert",
                    "role": "flagged",
                    "label_status": "flagged",
                    "summary": "Generic alert with no entity fields",
                    "source": "alerts.csv",
                }
            ],
            "total_event_count": 1,
            "truncated": False,
        }
    )


def test_thin_evidence_never_reaches_the_freeze_gate():
    evidence = _thin_package()
    output = LlmOutput.model_validate(
        {
            "output_version": "ai1-output-0.1",
            "incident_id": "inc-thin",
            "analysis_status": "complete",
            "summary": {
                "text": "One generic alert was raised.",
                "category": "evidence_supported",
                "cited_event_ids": ["E-001"],
            },
            "findings": [],
            "recommendations": [],
            "uncertainties": [{"statement": "No entity is known.", "missing_evidence": "Any log"}],
            "limitations": ["One event only."],
        }
    )
    grounding = check_output(output, evidence)
    assert grounding.valid
    assert grounding.grounding_rate == 1.0
    assert evidence_completeness(evidence) == 0.0
    assert compute_confidence(output, grounding, evidence) == GROUNDING_FLOOR
    assert GROUNDING_FLOOR < 0.75


def test_invalid_analysis_has_no_confidence(evidence, good_output):
    good_output["incident_id"] = "inc-other"
    output = LlmOutput.model_validate(good_output)
    grounding = check_output(output, evidence)
    assert compute_confidence(output, grounding, evidence) is None
