"""store_incidents: the one way C3's correlation results reach the database.

An incident belongs to the upload whose events it links. Storing is all or nothing: either
every incident of the call and all its event links are written, or nothing is. Storing an
incident that is already stored replaces it and its links, so running the correlation on the
same upload again gives the same rows (C3's incident IDs are deterministic).
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.contracts import Event, Incident, LabelStatus
from app.correlation.config import CorrelationConfig, load_config
from app.correlation.engine import correlate
from app.correlation.keys import key_values, key_values_of
from app.correlation.risk import EventConfidences, RiskConfig, score_incidents
from app.incidents.models import IncidentEventRow, IncidentRow, RiskAssessmentRow
from app.jobs.errors import JobLost
from app.jobs.queue import holds
from app.models import EventRow


class IncidentConflict(Exception):
    """An incident ID is already stored for another upload."""


class MissingEvents(Exception):
    """An incident links events that are not stored for its upload."""


def _row(upload_id: str, incident: Incident, config_version: str) -> dict:
    return {
        "incident_id": incident.incident_id,
        "upload_id": upload_id,
        "status": incident.status.value,
        "incident_type": incident.incident_type,
        "risk_score": incident.risk.score if incident.risk else None,
        "risk_level": incident.risk.level.value if incident.risk else None,
        "first_event_at": incident.first_event_at,
        "last_event_at": incident.last_event_at,
        "created_at": incident.created_at,
        "updated_at": incident.updated_at,
        "correlation_config_version": config_version,
        "data": incident.model_dump(mode="json"),
    }


def store_incidents(
    engine: Engine,
    upload_id: str,
    incidents: Sequence[Incident],
    config_version: str,
    owner: tuple[str, str] | None = None,
) -> int:
    """Store C3's incidents for one upload in one transaction. Returns how many were stored.

    Raises IncidentConflict if an incident ID is stored for another upload, and MissingEvents
    if an incident links an event that is not stored for this upload. Nothing is written then.
    `owner` is (job_id, worker_id) when a job stores them: the write happens only while that
    worker still holds the job, otherwise JobLost.
    """
    ids = [incident.incident_id for incident in incidents]
    if len(ids) != len(set(ids)):
        raise ValueError("incident IDs must be unique")
    if not incidents:
        return 0
    linked = {link.event_id for incident in incidents for link in incident.events}
    with Session(engine) as session, session.begin():
        if owner is not None and not holds(session.connection(), *owner):
            raise JobLost
        others = session.scalars(
            select(IncidentRow.incident_id).where(
                IncidentRow.incident_id.in_(ids), IncidentRow.upload_id != upload_id
            )
        ).all()
        if others:
            raise IncidentConflict(
                f"{len(others)} incident(s) are already stored for another upload, "
                f"for example {sorted(others)[0]}."
            )
        stored = set(
            session.scalars(
                select(EventRow.event_id).where(
                    EventRow.upload_id == upload_id, EventRow.event_id.in_(linked)
                )
            )
        )
        missing = sorted(linked - stored)
        if missing:
            raise MissingEvents(
                f"{len(missing)} linked event(s) are not stored for upload {upload_id}, "
                f"for example {', '.join(missing[:3])}."
            )
        rows = [_row(upload_id, incident, config_version) for incident in incidents]
        statement = insert(IncidentRow).values(rows)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[IncidentRow.incident_id],
                set_={
                    column: statement.excluded[column]
                    for column in rows[0]
                    if column != "incident_id"
                },
            )
        )
        session.execute(delete(IncidentEventRow).where(IncidentEventRow.incident_id.in_(ids)))
        session.execute(
            insert(IncidentEventRow),
            [
                {
                    "incident_id": incident.incident_id,
                    "event_id": link.event_id,
                    "upload_id": upload_id,
                    "role": link.role.value,
                    "link_keys": [key.value for key in link.link_keys],
                    "linked_at": link.linked_at,
                }
                for incident in incidents
                for link in incident.events
            ],
        )
        _record_assessments(session, upload_id, incidents)
    return len(incidents)


def _record_assessments(session: Session, upload_id: str, incidents: Sequence[Incident]) -> None:
    """One append-only risk_assessments row per scored incident (design 9A.3).

    A risk-v0 score (phase null) is recorded as phase initial: it is the score the incident was
    stored with. recorded_at is the database clock, so it never depends on the caller."""
    rows = [
        {
            "incident_id": incident.incident_id,
            "upload_id": upload_id,
            "phase": incident.risk.phase or "initial",
            "score": incident.risk.score,
            "level": incident.risk.level.value,
            "config_version": incident.risk.config_version,
            "computed_at": incident.risk.computed_at,
            "data": incident.risk.model_dump(mode="json"),
        }
        for incident in incidents
        if incident.risk is not None
    ]
    if rows:
        session.execute(insert(RiskAssessmentRow), rows)


def load_assessments(engine: Engine, incident_id: str) -> list[dict]:
    """Every recorded score of one incident, oldest first (the audit of design 9A.3)."""
    with Session(engine) as session:
        rows = session.execute(
            select(RiskAssessmentRow.phase, RiskAssessmentRow.recorded_at, RiskAssessmentRow.data)
            .where(RiskAssessmentRow.incident_id == incident_id)
            .order_by(RiskAssessmentRow.assessment_id)
        ).all()
    return [{"phase": p, "recorded_at": r, "risk": d} for p, r, d in rows]


def load_incident(engine: Engine, incident_id: str) -> Incident | None:
    with Session(engine) as session:
        data = session.scalar(
            select(IncidentRow.data).where(IncidentRow.incident_id == incident_id)
        )
    return None if data is None else Incident.model_validate(data)


def load_incidents(engine: Engine, upload_id: str) -> list[Incident]:
    """The stored incidents of one upload, earliest first."""
    with Session(engine) as session:
        rows = session.scalars(
            select(IncidentRow.data)
            .where(IncidentRow.upload_id == upload_id)
            .order_by(IncidentRow.first_event_at, IncidentRow.incident_id)
        ).all()
    return [Incident.model_validate(data) for data in rows]


# Rows read per round trip while matching unflagged events, and IDs per IN (...) list.
_STREAM_ROWS = 10_000
_ID_CHUNK = 1_000


def _events_that_can_matter(
    session: Session, upload_id: str, config: CorrelationConfig
) -> tuple[list[Event], datetime | None]:
    """The flagged events of an upload, plus only the other events that share a key value with
    one of them, and the latest event time of the whole upload (the risk score's clock W).

    An event that shares no key value with a flagged event can never become context
    (design note section 6), so leaving it out gives the same incidents with far less memory
    (decision D7 of 16 Nov 2026: 700,001 events took 2.7 GB in memory).
    """
    of_upload = EventRow.upload_id == upload_id
    flagged = [
        Event.model_validate(data)
        for data in session.scalars(
            select(EventRow.data).where(of_upload, EventRow.label_status == LabelStatus.FLAGGED)
        )
    ]
    reference = session.scalar(select(func.max(EventRow.timestamp)).where(of_upload))
    wanted = {value for event in flagged for value in key_values(event, config)}
    if not wanted:
        return flagged, reference
    keys = select(
        EventRow.event_id, EventRow.host, EventRow.src_ip, EventRow.dst_ip, EventRow.user
    ).where(of_upload, EventRow.label_status != LabelStatus.FLAGGED)
    matching = [
        event_id
        for event_id, *fields in session.execute(keys.execution_options(yield_per=_STREAM_ROWS))
        if not wanted.isdisjoint(key_values_of(*fields, config))
    ]
    context = []
    for start in range(0, len(matching), _ID_CHUNK):
        ids = matching[start : start + _ID_CHUNK]
        context += [
            Event.model_validate(data)
            for data in session.scalars(
                select(EventRow.data).where(of_upload, EventRow.event_id.in_(ids))
            )
        ]
    return flagged + context, reference


def correlate_upload(
    engine: Engine,
    upload_id: str,
    now: datetime,
    config: CorrelationConfig | None = None,
    owner: tuple[str, str] | None = None,
    risk: RiskConfig | None = None,
    confidences: EventConfidences | None = None,
) -> list[Incident]:
    """Run C3's correlation over the stored events of one upload, score every incident and
    store them (decision D1 of 16 Nov 2026: an incident is never stored without its score).

    Incident IDs are scoped to the upload (D4), so the same events in two uploads give two
    sets of incidents.
    """
    config = config or load_config()
    with Session(engine) as session:
        events, reference = _events_that_can_matter(session, upload_id, config)
    result = correlate(events, config, now, scope=upload_id)
    incidents = list(
        score_incidents(
            result.incidents,
            events,
            now,
            risk,
            config,
            reference=reference,
            confidences=confidences,
        )  # fmt: skip
    )
    store_incidents(engine, upload_id, incidents, result.config_version, owner)
    return incidents


def rescore_upload(
    engine: Engine,
    upload_id: str,
    now: datetime,
    risk: RiskConfig | None = None,
    config: CorrelationConfig | None = None,
    owner: tuple[str, str] | None = None,
    confidences: EventConfidences | None = None,
) -> list[Incident]:
    """Score an upload's stored incidents again, for example after risk.toml changed, or with
    the model's C (risk-v1 phase 2). Every new score is appended to risk_assessments.

    The grouping is not run again: the stored incidents keep their events and IDs, and only
    their risk changes.
    """
    config = config or load_config()
    with Session(engine) as session:
        rows = session.execute(
            select(IncidentRow.data, IncidentRow.correlation_config_version)
            .where(IncidentRow.upload_id == upload_id)
            .order_by(IncidentRow.first_event_at, IncidentRow.incident_id)
        ).all()
        if not rows:
            return []
        events, reference = _events_that_can_matter(session, upload_id, config)
    incidents = [Incident.model_validate(data) for data, _ in rows]
    scored = list(
        score_incidents(
            incidents, events, now, risk, config, reference=reference, confidences=confidences
        )
    )
    # The grouping is unchanged, so each incident keeps the correlation version it was built with.
    by_version: dict[str, list[Incident]] = {}
    for incident, (_, version) in zip(scored, rows, strict=True):
        by_version.setdefault(version, []).append(incident)
    for version, batch in by_version.items():
        store_incidents(engine, upload_id, batch, version, owner)
    return scored
