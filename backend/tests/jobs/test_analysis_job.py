"""C1 analysis job (decisions F1, F5, F6, F8): upload -> ingest -> one analysis job per incident
-> stored report -> response engine. Runs on PostgreSQL with the stub model backend."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analysis.backends import BackendError, Generation
from app.analysis.models import AnalysisReportRow
from app.analysis.stub import StubGenerator
from app.api.schemas import Job, JobKind
from app.contracts import AnalysisStatus, AuditEventType, Incident, IncidentStatus
from app.incidents.models import IncidentRow
from app.jobs import analysis
from app.jobs.queue import utcnow
from app.models import JobRow
from app.response.models import AuditRow
from app.worker.runner import RUNNERS, run_once


@pytest.fixture
def engine(engine):
    """The jobs conftest engine, with the incident, report and response tables emptied too."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE analysis_reports, masking_maps, incident_events, incidents, "
                "audit_records, response_actions, response_windows, incident_status_history, "
                "incident_lifecycle RESTART IDENTITY CASCADE"
            )
        )
    return engine


class Silent:
    """A backend that never answers (check X1), like an unreachable model service."""

    generated_by, model_id = "hpc", "test-unreachable"

    def generate(self, messages, evidence) -> Generation:
        raise BackendError("hpc_timeout: no answer within 1 s")


class Babbling:
    """A backend that answers, but never with JSON (check P1), so every report fails."""

    generated_by, model_id = "local", "test-babble"

    def generate(self, messages, evidence) -> Generation:
        return Generation("I think this is fine.")


def runners(generator_factory):
    def _analysis(engine, job, worker_id, settings, clock):
        return analysis.run_analysis_job(
            engine, job, worker_id, settings, clock, generator_factory=generator_factory
        )

    return RUNNERS | {JobKind.ANALYSIS: _analysis}


def drain(engine, settings, generator_factory=StubGenerator) -> int:
    ran = 0
    while run_once(engine, "worker-test", settings, utcnow, runners(generator_factory)):
        ran += 1
    return ran


def jobs(engine, kind: str) -> list[JobRow]:
    with Session(engine) as session:
        return list(session.scalars(select(JobRow).where(JobRow.kind == kind)).all())


def incidents(engine) -> list[Incident]:
    with Session(engine) as session:
        return [Incident.model_validate(d) for d in session.scalars(select(IncidentRow.data))]


def lifecycle(engine, incident_id: str) -> IncidentStatus | None:
    return analysis._response_engine(engine).status_of(incident_id)


def test_upload_ends_with_a_report_and_a_lifecycle_for_every_incident(
    upload, fixture_events, client, engine, settings
):
    upload(fixture_events.read_bytes())
    drain(engine, settings)

    stored = incidents(engine)
    done = jobs(engine, "analysis")
    assert stored and len(done) == len(stored)
    assert {j.state for j in done} == {"done"}
    for job in done:
        api = Job.model_validate(client.get(f"/jobs/{job.job_id}").json())
        assert api.analysis is not None and api.analysis.report_valid
        assert api.analysis.generated_by == "mock" and api.analysis.problems == []
    with Session(engine) as session:
        reports = {r.incident_id: r for r in session.scalars(select(AnalysisReportRow))}
    for incident in stored:
        assert incident.analysis_status == AnalysisStatus.SUCCEEDED
        assert reports[incident.incident_id].report_id == incident.latest_report_id
        # Registered (T01), analysed (T02) and handed to the freeze gate (T03 or T04).
        assert lifecycle(engine, incident.incident_id) not in (
            None,
            IncidentStatus.NEW,
            IncidentStatus.UNDER_ANALYSIS,
        )
    # The fixture's High incident with a target host freezes: a real response window opens.
    with Session(engine) as session:
        opened = session.scalars(
            select(AuditRow.incident_id).where(
                AuditRow.event_type == AuditEventType.RESPONSE_WINDOW_OPENED
            )
        ).all()
    assert len(opened) >= 1


def test_analysis_jobs_are_queued_highest_risk_first(upload, fixture_events, engine, settings):
    upload(fixture_events.read_bytes())
    run_once(engine, "worker-test", settings, utcnow, runners(StubGenerator))  # ingest only
    with Session(engine) as session:
        queued = session.scalars(
            select(JobRow).where(JobRow.kind == "analysis").order_by(JobRow.created_at)
        ).all()
        score = dict(session.execute(select(IncidentRow.incident_id, IncidentRow.risk_score)).all())
    order = [score[j.payload["incident_id"]] for j in queued]
    assert order == sorted(order, key=lambda s: -(s if s is not None else -1))


def test_a_silent_model_is_retried_then_fails_and_never_freezes(
    upload, fixture_events, client, engine, settings
):
    upload(fixture_events.read_bytes())
    drain(engine, settings, Silent)

    failed = jobs(engine, "analysis")
    assert failed and {j.state for j in failed} == {"failed"}
    for job in failed:
        assert job.attempts == job.max_attempts == settings.job_max_attempts
        assert job.error_code == "hpc_timeout"  # the backend's own code, not a generic one
    for incident in incidents(engine):
        assert incident.analysis_status == AnalysisStatus.FAILED and incident.confidence is None
        assert lifecycle(engine, incident.incident_id) == IncidentStatus.UNDER_ANALYSIS
    with Session(engine) as session:
        audited = session.scalars(
            select(AuditRow.incident_id).where(
                AuditRow.event_type == AuditEventType.ANALYSIS_FAILED
            )
        ).all()
    assert sorted(audited) == sorted(i.incident_id for i in incidents(engine))


def test_a_report_that_fails_the_checks_is_a_result_not_a_job_failure(
    upload, fixture_events, client, engine, settings
):
    upload(fixture_events.read_bytes())
    drain(engine, settings, Babbling)

    for job in jobs(engine, "analysis"):
        assert job.state == "done" and job.attempts == 1
        api = Job.model_validate(client.get(f"/jobs/{job.job_id}").json())
        assert api.analysis is not None and not api.analysis.report_valid
        assert any("P1" in p for p in api.analysis.problems)
        assert api.analysis.report_id is None and api.analysis.confidence is None
    for incident in incidents(engine):
        assert incident.analysis_status == AnalysisStatus.FAILED
        assert lifecycle(engine, incident.incident_id) == IncidentStatus.UNDER_ANALYSIS  # T05


def test_rerun_endpoint_queues_one_job_and_a_double_click_gets_the_same(
    upload, fixture_events, client, engine, settings
):
    upload(fixture_events.read_bytes())
    drain(engine, settings)
    incident_id = incidents(engine)[0].incident_id

    first = client.post(f"/incidents/{incident_id}/analysis", json={"force": True})
    second = client.post(f"/incidents/{incident_id}/analysis")
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert first.headers["Location"] == first.json()["status_url"]

    before = len(_report_ids(engine, incident_id))
    assert drain(engine, settings) == 1
    done = Job.model_validate(client.get(first.json()["status_url"]).json())
    assert done.state == "done" and done.analysis is not None and done.analysis.report_valid
    # force=True skipped the cache, so a second report is stored; the lifecycle is unchanged.
    assert len(_report_ids(engine, incident_id)) == before + 1


def test_rerun_endpoint_refuses_an_unknown_incident(client, engine):
    response = client.post("/incidents/inc-does-not-exist/analysis")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_backfill_queues_only_incidents_without_an_analysis_job(
    upload, fixture_events, engine, settings
):
    upload(fixture_events.read_bytes())
    drain(engine, settings)
    with engine.begin() as connection:  # as if stored before the analysis job existed
        connection.execute(text("DELETE FROM jobs WHERE kind = 'analysis'"))
    stored = {i.incident_id for i in incidents(engine)}

    assert set(analysis.backfill(engine, utcnow(), 3)) == stored
    assert analysis.backfill(engine, utcnow(), 3) == []  # already queued
    drain(engine, settings)
    assert {j.state for j in jobs(engine, "analysis")} == {"done"}


def _report_ids(engine, incident_id: str) -> list[str]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AnalysisReportRow.report_id).where(
                    AnalysisReportRow.incident_id == incident_id
                )
            )
        )
