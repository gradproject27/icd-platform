"""risk-v1 step 6b: the confidence job on HPC (user decision of 26 Nov 2026), fake cluster."""

from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analysis.backends import BackendError
from app.analysis.stub import StubGenerator
from app.api.schemas import JobKind, JobState
from app.confidence.handoff import ConfidenceOutput, EventValue, build_input
from app.contracts import Incident, RiskFlag
from app.incidents.models import IncidentRow
from app.incidents.store import load_assessments
from app.jobs import analysis
from app.jobs.confidence import run_confidence_job
from app.jobs.queue import utcnow
from app.models import JobRow
from app.worker.runner import RUNNERS, run_once

NF_SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "ingest" / "nf-v3-sample.csv"


@pytest.fixture
def engine(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE risk_assessments, analysis_reports, masking_maps, incident_events, "
                "incidents, audit_records, response_actions, response_windows, "
                "incident_status_history, incident_lifecycle RESTART IDENTITY CASCADE"
            )
        )
    return engine


class FakeCluster:
    """Answers every event with C 0.4 (p_clf 0.4, p_llm 0.5); records what it was sent."""

    sent: list[dict] = []

    def __init__(self) -> None:
        self.on_stage = None

    def submit(self, data):
        FakeCluster.sent.append(data)
        return ConfidenceOutput(
            request_id=data["request_id"], version="test-models",
            versions={"classifier": "clf-test", "stacker": "stack-test"},
            events={e["event_id"]: EventValue(c=0.4, p_clf=0.4, p_llm=0.5) for e in data["events"]},
        )  # fmt: skip


class SilentCluster:
    def __init__(self) -> None:
        self.on_stage = None

    def submit(self, data):
        raise BackendError("hpc_timeout: no answer within 1 s")


def runners(cluster):
    def _confidence(engine, job, worker_id, settings, clock):
        return run_confidence_job(engine, job, worker_id, settings, clock, batch_factory=cluster)

    def _analysis(engine, job, worker_id, settings, clock):
        return analysis.run_analysis_job(
            engine, job, worker_id, settings, clock, generator_factory=StubGenerator
        )

    return RUNNERS | {JobKind.CONFIDENCE: _confidence, JobKind.ANALYSIS: _analysis}


def drain(engine, settings, cluster) -> None:
    while run_once(engine, "worker-test", settings, utcnow, runners(cluster)):
        pass


def jobs(engine, kind: str) -> list[JobRow]:
    with Session(engine) as session:
        return list(session.scalars(select(JobRow).where(JobRow.kind == kind)).all())


def incidents(engine) -> list[Incident]:
    with Session(engine) as session:
        return [Incident.model_validate(d) for d in session.scalars(select(IncidentRow.data))]


@pytest.fixture
def nf_upload(upload, monkeypatch):
    monkeypatch.setenv("ICD_CONFIDENCE_BACKEND", "hpc_batch")
    return upload(NF_SAMPLE.read_bytes(), "nf-v3-sample.csv", "nf-unsw-nb15-v3")


def test_phase_two_on_hpc_then_the_analysis(nf_upload, engine, settings):
    FakeCluster.sent.clear()
    drain(engine, settings, FakeCluster)
    assert [j.state for j in jobs(engine, "confidence")] == [JobState.DONE.value]
    stored = incidents(engine)
    assert stored and len(jobs(engine, "analysis")) == len(stored)
    for incident in stored:
        assert incident.risk.phase == "final"
        assert incident.risk.config_version.endswith("+test-models")
        assert RiskFlag.LLM_PENDING not in incident.risk.flags
        records = load_assessments(engine, incident.incident_id)
        first, last = records[0]["risk"], records[-1]["risk"]
        assert records[0]["phase"] == "initial" and records[-1]["phase"] == "final"
        assert {"llm_pending", "confidence_fixed"} <= set(first["flags"])
        assert last["confidence_versions"]["stacker"] == "stack-test"
    text_sent = str(FakeCluster.sent)
    for value in ("192.0.2", "198.51.100", "203.0.113"):
        assert value not in text_sent  # features and masked descriptions only


def test_no_answer_retries_then_keeps_the_initial_score_flagged(nf_upload, engine, settings):
    drain(engine, settings, SilentCluster)
    job = jobs(engine, "confidence")[0]
    assert job.state == JobState.DONE.value and job.attempts == settings.job_max_attempts
    stored = incidents(engine)
    assert stored and len(jobs(engine, "analysis")) == len(stored)  # the report still runs
    for incident in stored:
        assert incident.risk.phase == "initial"
        assert RiskFlag.LLM_UNAVAILABLE in incident.risk.flags
        assert RiskFlag.CONFIDENCE_FIXED in incident.risk.flags
        assert "final" not in [r["phase"] for r in load_assessments(engine, incident.incident_id)]


def test_backend_off_queues_no_confidence_job(upload, engine, settings, monkeypatch):
    monkeypatch.delenv("ICD_CONFIDENCE_BACKEND", raising=False)
    upload(NF_SAMPLE.read_bytes(), "nf-v3-sample.csv", "nf-unsw-nb15-v3")
    drain(engine, settings, FakeCluster)
    assert jobs(engine, "confidence") == []
    assert all(i.risk.phase is None for i in incidents(engine))


def test_other_datasets_queue_no_confidence_job(upload, fixture_events, engine, settings,
                                                monkeypatch):  # fmt: skip
    monkeypatch.setenv("ICD_CONFIDENCE_BACKEND", "hpc_batch")
    upload(fixture_events.read_bytes())
    drain(engine, settings, FakeCluster)
    assert jobs(engine, "confidence") == []


def test_input_has_47_features_and_masked_groups(nf_upload, engine, settings):
    drain(engine, settings, FakeCluster)
    stored = incidents(engine)
    from app.correlation.config import load_config
    from app.incidents.store import _events_that_can_matter

    with Session(engine) as session:
        events, _ = _events_that_can_matter(session, stored[0].events and nf_upload["upload_id"],
                                            load_config())  # fmt: skip
    data = build_input("req-1", stored, {e.event_id: e for e in events})
    assert data["events"] and all(len(e["features"]) == 47 for e in data["events"])
    assert data["groups"] and all(g["evidence"]["source"] == "SRC" for g in data["groups"])
    grouped = {i for g in data["groups"] for i in g["event_ids"]}
    assert grouped == {e["event_id"] for e in data["events"]}
