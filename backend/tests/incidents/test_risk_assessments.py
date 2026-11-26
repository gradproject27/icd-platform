"""risk-v1 step 6b: every stored score is an append-only record (design 9A.3, RV1-D17)."""

from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.confidence.values import Confidence
from app.contracts import RiskFlag
from app.correlation import is_high
from app.correlation.risk import EventConfidences, load_risk_config
from app.incidents.store import correlate_upload, load_assessments, rescore_upload
from tests.incidents.test_incident_store import NOW, stored_upload


def test_correlating_records_one_initial_assessment_per_incident(engine):
    incidents = correlate_upload(engine, stored_upload(engine), NOW)
    for incident in incidents:
        records = load_assessments(engine, incident.incident_id)
        assert [r["phase"] for r in records] == ["initial"]
        assert records[0]["risk"] == incident.risk.model_dump(mode="json")


def test_rescoring_appends_and_keeps_the_earlier_score(engine):
    upload_id = stored_upload(engine)
    before = {i.incident_id: i for i in correlate_upload(engine, upload_id, NOW)}
    stricter = replace(load_risk_config(), unknown_impact=0.33)
    after = rescore_upload(engine, upload_id, NOW, risk=stricter)
    for incident in after:
        records = load_assessments(engine, incident.incident_id)
        assert len(records) == 2
        assert records[0]["risk"]["score"] == before[incident.incident_id].risk.score
        assert records[1]["risk"]["score"] == incident.risk.score


def test_records_cannot_be_changed_or_deleted(engine):
    correlate_upload(engine, stored_upload(engine), NOW)
    for statement in ("UPDATE risk_assessments SET score = 0", "DELETE FROM risk_assessments"):
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
            connection.execute(text(statement))


def test_the_records_outlive_a_cleared_upload(engine):
    from app.jobs.queue import clear_upload_rows

    upload_id = stored_upload(engine)
    incident = correlate_upload(engine, upload_id, NOW)[0]
    clear_upload_rows(engine, upload_id)
    assert len(load_assessments(engine, incident.incident_id)) == 1


def test_phase_and_versions_are_stored_with_a_model_score(engine):
    upload_id = stored_upload(engine)
    first = correlate_upload(engine, upload_id, NOW)
    flagged = {link.event_id for i in first for link in i.events if link.role.value == "flagged"}
    confidences = EventConfidences(
        {e: Confidence(0.9, 0.9, None, ("llm_pending",)) for e in flagged},
        "clf-1+stack-1",
        phase="initial",
        versions={"classifier": "clf-1", "stacker": "stack-1"},
    )
    rescored = rescore_upload(engine, upload_id, NOW, confidences=confidences)
    record = load_assessments(engine, rescored[0].incident_id)[-1]
    assert record["phase"] == "initial"
    assert record["risk"]["confidence_versions"] == {"classifier": "clf-1", "stacker": "stack-1"}
    assert "llm_pending" in record["risk"]["flags"]


def test_an_initial_high_score_can_start_a_freeze_with_the_pending_flag():
    # User decision of 26 Nov 2026: the freeze precondition reads the current score, initial or
    # final; the llm_pending flag stays on the incident so the decision panel shows it.
    from app.contracts import RiskAssessment, RiskFactor, RiskLevel

    risk = RiskAssessment(
        score=85, level=RiskLevel.HIGH, config_version="risk-v0+x", computed_at=NOW,
        factors=[RiskFactor(name="likelihood", value=0.85, weight=1.0, contribution=85.0)],
        flags=[RiskFlag.LLM_PENDING], phase="initial",
    )  # fmt: skip
    assert is_high(risk)
