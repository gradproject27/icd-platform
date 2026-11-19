"""Stored reports and the database report cache (AI1, steps 5 and 11; table `analysis_reports`).

    attempt = analyze_incident(engine, incident_id, generator, clock)   # the analysis job's call

`analyze_incident` is the one call C1's analysis job makes for a stored incident:

1. C2's builder makes the masked package from the stored rows and stores its masking map.
2. `analyze_package` checks the cache, sends prompt v2, retries once on a format error, and
   checks the answer (service.py).
3. A new valid report is stored here (the stored report is the cache entry).
4. The incident's analysis fields are updated in the same transaction (C5 decision D2):
   succeeded -> confidence + latest_report_id; failed -> confidence null, so the incident
   can never freeze on a failed analysis. analysis_attempts counts every attempt.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.analysis.backends import Generator
from app.analysis.cache import CacheEntry
from app.analysis.incident_fields import apply_result
from app.analysis.models import AnalysisReportRow
from app.analysis.service import AnalysisAttempt, analyze_package
from app.contracts import AnalysisReport, Incident
from app.evidence.store import IncidentNotStored, build_and_store_for_incident
from app.incidents.models import IncidentRow


def _entry(row: AnalysisReportRow) -> CacheEntry:
    return CacheEntry(
        key=row.cache_key,
        report=AnalysisReport.model_validate(row.report),
        raw_output=row.raw_output,
        stored_at=row.created_at,
    )


class DbReportCache:
    """The cache over `analysis_reports`: get returns the newest report stored for a key."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.pending: list[CacheEntry] = []

    def get(self, key: str) -> CacheEntry | None:
        with Session(self.engine) as session:
            row = session.scalars(
                select(AnalysisReportRow)
                .where(AnalysisReportRow.cache_key == key)
                .order_by(AnalysisReportRow.created_at.desc(), AnalysisReportRow.report_id)
                .limit(1)
            ).first()
            return None if row is None else _entry(row)

    def put(self, entry: CacheEntry) -> None:
        # Written by record_attempt together with the incident update, in one transaction.
        self.pending.append(entry)


def _report_row(attempt: AnalysisAttempt, entry: CacheEntry) -> AnalysisReportRow:
    report = entry.report
    return AnalysisReportRow(
        report_id=report.report_id,
        incident_id=report.incident_id,
        evidence_package_id=report.evidence_package_id,
        cache_key=entry.key,
        generated_by=report.generated_by,
        model_id=report.model_id,
        prompt_version=report.prompt_version,
        confidence=report.confidence,
        created_at=entry.stored_at,
        report=report.model_dump(mode="json"),
        raw_output=entry.raw_output,
        tries=[t.record() for t in attempt.tries],
    )


def record_attempt(
    engine: Engine,
    attempt: AnalysisAttempt,
    now: datetime,
    new_entries: list[CacheEntry] | None = None,
) -> Incident:
    """Store the attempt's new report (if any) and update the incident, in one transaction.

    The incident row is locked while it is updated, so two attempts cannot lose a count.
    Returns the updated incident.
    """
    with Session(engine) as session, session.begin():
        row = session.scalars(
            select(IncidentRow).where(IncidentRow.incident_id == attempt.incident_id)
            .with_for_update()
        ).first()  # fmt: skip
        if row is None:
            raise IncidentNotStored(attempt.incident_id)
        for entry in new_entries or []:
            session.add(_report_row(attempt, entry))
        updated = apply_result(Incident.model_validate(row.data), attempt.result, now)
        session.execute(
            update(IncidentRow)
            .where(IncidentRow.incident_id == attempt.incident_id)
            .values(data=updated.model_dump(mode="json"), updated_at=updated.updated_at)
        )
    return updated


def analyze_incident(
    engine: Engine,
    incident_id: str,
    generator: Generator,
    clock: Callable[[], datetime],
    *,
    force: bool = False,
) -> AnalysisAttempt:
    """Analyse one stored incident end to end (module docstring). force=True skips the cache."""
    evidence = build_and_store_for_incident(engine, incident_id, clock())
    cache = DbReportCache(engine)
    attempt = analyze_package(evidence, generator, clock=clock, cache=cache, force=force)
    record_attempt(engine, attempt, clock(), cache.pending)
    return attempt


def load_report(engine: Engine, report_id: str) -> AnalysisReport | None:
    """One stored report (masked; the API un-masks it for display with C2's unmask_report)."""
    with Session(engine) as session:
        data = session.scalar(
            select(AnalysisReportRow.report).where(AnalysisReportRow.report_id == report_id)
        )
    return None if data is None else AnalysisReport.model_validate(data)


def latest_report(engine: Engine, incident_id: str) -> AnalysisReport | None:
    """The report the incident's latest_report_id names, or None (no valid analysis yet)."""
    with Session(engine) as session:
        data = session.scalar(
            select(IncidentRow.data).where(IncidentRow.incident_id == incident_id)
        )
    if data is None:
        raise IncidentNotStored(incident_id)
    report_id = Incident.model_validate(data).latest_report_id
    return None if report_id is None else load_report(engine, report_id)
