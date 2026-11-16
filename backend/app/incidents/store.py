"""store_incidents: the one way C3's correlation results reach the database.

An incident belongs to the upload whose events it links. Storing is all or nothing: either
every incident of the call and all its event links are written, or nothing is. Storing an
incident that is already stored replaces it and its links, so running the correlation on the
same upload again gives the same rows (C3's incident IDs are deterministic).
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.contracts import Event, Incident
from app.correlation.config import CorrelationConfig, load_config
from app.correlation.engine import correlate, incident_id_for
from app.incidents.models import IncidentEventRow, IncidentRow
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
    return len(incidents)


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


def scoped(upload_id: str, incident: Incident) -> Incident:
    """The incident with its ID scoped to its upload.

    C3 derives the ID from the event that started the incident, and event IDs repeat across
    uploads (the same file uploaded twice, or two files with the same record numbers), so two
    uploads would otherwise produce the same incident ID. The ID stays deterministic: the same
    upload always gives the same IDs.
    """
    start = incident.events[0].event_id  # correlate() lists the starting event first
    return incident.model_copy(update={"incident_id": incident_id_for(f"{upload_id}/{start}")})


def correlate_upload(
    engine: Engine,
    upload_id: str,
    now: datetime,
    config: CorrelationConfig | None = None,
    owner: tuple[str, str] | None = None,
) -> list[Incident]:
    """Run C3's correlation over the stored events of one upload and store the incidents."""
    config = config or load_config()
    with Session(engine) as session:
        data = session.scalars(select(EventRow.data).where(EventRow.upload_id == upload_id)).all()
    result = correlate([Event.model_validate(item) for item in data], config, now)
    incidents = [scoped(upload_id, incident) for incident in result.incidents]
    store_incidents(engine, upload_id, incidents, result.config_version, owner)
    return incidents
