import json

import pytest
from pydantic import ValidationError

from app.contracts import AnalysisReport

REQUIRED = [
    "report_id",
    "incident_id",
    "evidence_package_id",
    "generated_at",
    "generated_by",
    "summary",
    "findings",
    "recommendations",
    "uncertainty",
    "confidence",
]


@pytest.fixture
def data(load_example):
    return load_example("analysis-report")


def test_example_round_trips(data):
    report = AnalysisReport.model_validate_json(json.dumps(data))
    assert AnalysisReport.model_validate_json(report.model_dump_json()) == report


@pytest.mark.parametrize("field", REQUIRED)
def test_missing_required_field_is_rejected(data, field):
    del data[field]
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


def test_sections_not_determined_are_null(data):
    for field in ("attack_type", "sequence", "weaknesses", "impact", "risk_justification"):
        del data[field]
    data["findings"] = []
    data["recommendations"] = []
    report = AnalysisReport.model_validate(data)
    assert report.sequence is None
    assert json.loads(report.model_dump_json())["impact"] is None


def test_evidence_supported_finding_without_citation_is_rejected(data):
    data["findings"][0]["cited_event_ids"] = []
    with pytest.raises(ValidationError, match="evidence_supported"):
        AnalysisReport.model_validate(data)


@pytest.mark.parametrize("category", ["likely_interpretation", "hypothesis"])
def test_other_findings_may_cite_nothing(data, category):
    data["findings"][1] = {"statement": "x", "category": category, "cited_event_ids": []}
    assert AnalysisReport.model_validate(data).findings[1].cited_event_ids == []


@pytest.mark.parametrize("orders", [[1, 3], [2, 3], [2, 1]])
def test_sequence_with_gaps_is_rejected(data, orders):
    for step, order in zip(data["sequence"], orders, strict=True):
        step["order"] = order
    with pytest.raises(ValidationError, match="no gaps"):
        AnalysisReport.model_validate(data)


def test_empty_sequence_is_rejected(data):
    data["sequence"] = []
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


def test_sequence_step_must_cite(data):
    data["sequence"][0]["cited_event_ids"] = []
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


def test_empty_weaknesses_list_is_rejected(data):
    data["weaknesses"] = []
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


@pytest.mark.parametrize("field", ["confidence", "model_self_rating"])
def test_rating_above_one_is_rejected(data, field):
    data[field] = 1.5
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


def test_unknown_backend_is_rejected(data):
    data["generated_by"] = "cloud"
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


def test_report_has_no_risk_score(data):
    data["risk_score"] = 74
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


def test_naive_timestamp_is_rejected(data):
    data["generated_at"] = "2026-03-14T10:02:15"
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)


@pytest.mark.parametrize("field", ["model_id", "prompt_version", "attack_type", "impact"])
def test_empty_optional_string_is_rejected(data, field):
    data[field] = ""
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(data)
