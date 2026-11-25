"""Incident, response-window and decision endpoints for the dashboard (Step 8, W3-D9).

Thin wiring only: the incidents come from C1's store (migration 0005, C3's correlation and risk
as stored), the status, window, decisions and audit from C5's response engine. Nothing here
computes a risk score, picks a scenario or changes the engine's rules.

Until login exists (C5, T2-15), a decision is made as the development identity in ICD_DEV_USER
and ICD_DEV_ROLE (decision S8-D4); without them every decision is refused with 403.
"""

import asyncio
import os
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.analysis.grounding import MASKED_TOKEN
from app.analysis.store import latest_report
from app.api.errors import ApiException
from app.api.schemas import (
    AuditTrail,
    ContainmentList,
    CurrentUser,
    DecisionRecord,
    DecisionRequest,
    EntityRiskIncident,
    EntityRiskItem,
    EntityRiskList,
    ErrorCode,
    IncidentEntities,
    IncidentEventItem,
    IncidentEventList,
    IncidentKeyFacts,
    IncidentList,
    IncidentSummary,
    JobAccepted,
    NotificationList,
    OriginalRecord,
    RecentDecision,
    RecentDecisionList,
    ResponseWindow,
    ScenarioCatalogue,
    ScenarioItem,
    SimulatedContainment,
)
from app.contracts import (
    AnalysisReport,
    AuditEventType,
    AuditRecord,
    Event,
    Incident,
    IncidentStatus,
    ScenarioId,
    UserRole,
)
from app.correlation.entity_risk import (
    EntityRiskConfig,
    EntityRiskReport,
    entity_risk,
    load_entity_risk_config,
)
from app.db import get_engine
from app.evidence.store import load_masking_map, unmask_report
from app.incidents.key_facts import key_facts
from app.incidents.models import IncidentEventRow, IncidentRow
from app.ingest.lines import read_original
from app.jobs.analysis import queue_analysis
from app.jobs.queue import utcnow
from app.models import EventRow
from app.response.clock import DatabaseClock
from app.response.engine import DecisionRefused, RefusalReason, ResponseEngine, WindowView
from app.response.engine import DecisionType as EngineDecision
from app.response.lifecycle import TransitionRefused
from app.response.models import AuditRow, IncidentLifecycleRow
from app.response.scenario_meta import load_scenario_meta
from app.settings import get_settings

router = APIRouter()

# Incidents per list answer. Filters and sort run in the browser (decision D8).
MAX_INCIDENTS = 1000


def response_engine() -> ResponseEngine:
    """C5's engine on the database clock; tests override this with a FakeClock."""
    engine = get_engine()
    return ResponseEngine(engine, DatabaseClock(engine))


EngineDep = Annotated[ResponseEngine, Depends(response_engine)]


def _not_found(incident_id: str) -> ApiException:
    return ApiException(404, ErrorCode.NOT_FOUND, f"No incident with ID {incident_id} exists.")


def _entities(rows: Iterable[tuple[str | None, str | None, str | None, str | None]]):
    hosts, users, ips = set(), set(), set()
    for host, user, src_ip, dst_ip in rows:
        if host:
            hosts.add(host)
        if user:
            users.add(user)
        ips.update(ip for ip in (src_ip, dst_ip) if ip)
    return IncidentEntities(hosts=sorted(hosts), users=sorted(users), ips=sorted(ips))


def _summaries(engine: Engine, rows: list[IncidentRow]) -> list[IncidentSummary]:
    """Incident rows with their entities and the engine's status and recommendation."""
    ids = [row.incident_id for row in rows]
    if not ids:
        return []
    with Session(engine) as session:
        entity_rows = session.execute(
            select(
                IncidentEventRow.incident_id,
                EventRow.host,
                EventRow.user,
                EventRow.src_ip,
                EventRow.dst_ip,
            )
            .join(
                EventRow,
                (EventRow.upload_id == IncidentEventRow.upload_id)
                & (EventRow.event_id == IncidentEventRow.event_id),
            )
            .where(IncidentEventRow.incident_id.in_(ids))
        ).all()
        lifecycle = {
            row.incident_id: row
            for row in session.scalars(
                select(IncidentLifecycleRow).where(IncidentLifecycleRow.incident_id.in_(ids))
            )
        }
    by_incident = defaultdict(list)
    for incident_id, *values in entity_rows:
        by_incident[incident_id].append(tuple(values))
    items = []
    for row in rows:
        incident = Incident.model_validate(row.data)
        tracked = lifecycle.get(row.incident_id)
        if tracked is not None:
            # C5's engine owns the status once it tracks the incident (response-engine.md 6).
            incident = incident.model_copy(update={"status": IncidentStatus(tracked.status)})
        items.append(
            IncidentSummary(
                incident=incident,
                entities=_entities(by_incident[row.incident_id]),
                recommended_scenario_id=(
                    ScenarioId(tracked.recommended_scenario_id)
                    if tracked is not None and tracked.recommended_scenario_id
                    else None
                ),
            )
        )
    return items


def _incident_row(session: Session, incident_id: str) -> IncidentRow:
    row = session.get(IncidentRow, incident_id)
    if row is None:
        raise _not_found(incident_id)
    return row


@router.get("/incidents", response_model=IncidentList)
def list_incidents(
    upload_id: Annotated[str | None, Query(max_length=128)] = None,
) -> IncidentList:
    engine = get_engine()
    with Session(engine) as session:
        query = select(IncidentRow).order_by(
            IncidentRow.first_event_at.desc(), IncidentRow.incident_id
        )
        if upload_id is not None:
            query = query.where(IncidentRow.upload_id == upload_id)
        rows = list(session.scalars(query.limit(MAX_INCIDENTS)))
    return IncidentList(items=_summaries(engine, rows))


@router.get("/entity-risk", response_model=EntityRiskList)
def entity_risk_list(
    upload_id: Annotated[str | None, Query(max_length=128)] = None,
) -> EntityRiskList:
    """P3: the entity roll-up over the stored incidents (of one upload, if given). A read."""
    config = load_entity_risk_config()
    with Session(get_engine()) as session:
        query = select(IncidentRow).order_by(IncidentRow.last_event_at.desc())
        if upload_id is not None:
            query = query.where(IncidentRow.upload_id == upload_id)
        rows = list(session.scalars(query.limit(MAX_INCIDENTS)))
        events = [
            Event.model_validate(data)
            for data in session.scalars(
                select(EventRow.data)
                .join(
                    IncidentEventRow,
                    (EventRow.upload_id == IncidentEventRow.upload_id)
                    & (EventRow.event_id == IncidentEventRow.event_id),
                )
                .where(IncidentEventRow.incident_id.in_([r.incident_id for r in rows]))
            )
        ]
    report = entity_risk([Incident.model_validate(r.data) for r in rows], events, config)
    return entity_risk_answer(report, config)


def entity_risk_answer(report: EntityRiskReport, config: EntityRiskConfig) -> EntityRiskList:
    """The API shape of an entity roll-up report (also writes the docs/api example)."""
    return EntityRiskList(
        config_version=report.config_version,
        tactics_config_version=report.tactics_config_version,
        window_start=report.window_start,
        window_end=report.window_end,
        score_threshold=config.score_threshold,
        tactics_threshold=config.tactics_threshold,
        items=[
            EntityRiskItem(
                entity=item.entity,
                score=item.score,
                level=item.level,
                incident_count=item.incident_count,
                incidents=[EntityRiskIncident(incident_id=i, score=s) for i, s in item.incidents],
                tactics=item.tactics,
                flags=item.flags,
            )
            for item in report.items
        ],
    )


@router.get("/incidents/{incident_id}", response_model=IncidentSummary)
def get_incident(incident_id: str) -> IncidentSummary:
    engine = get_engine()
    with Session(engine) as session:
        row = _incident_row(session, incident_id)
    return _summaries(engine, [row])[0]


@router.get("/incidents/{incident_id}/events", response_model=IncidentEventList)
def incident_events(incident_id: str) -> IncidentEventList:
    with Session(get_engine()) as session:
        row = _incident_row(session, incident_id)
        incident = Incident.model_validate(row.data)
        stored = {
            event_id: data
            for event_id, data in session.execute(
                select(EventRow.event_id, EventRow.data)
                .join(
                    IncidentEventRow,
                    (EventRow.upload_id == IncidentEventRow.upload_id)
                    & (EventRow.event_id == IncidentEventRow.event_id),
                )
                .where(IncidentEventRow.incident_id == incident_id)
            )
        }
    items = [
        IncidentEventItem(
            event=Event.model_validate(stored[link.event_id]),
            role=link.role,
            link_keys=link.link_keys,
        )
        for link in incident.events
        if link.event_id in stored
    ]
    items.sort(key=lambda item: (item.event.timestamp, item.event.event_id))
    return IncidentEventList(items=items)


@router.get("/incidents/{incident_id}/key-facts", response_model=IncidentKeyFacts)
def incident_key_facts(incident_id: str, response: EngineDep) -> IncidentKeyFacts:
    """Start, assets and indicators computed by code from the flagged events (P1); no model."""
    with Session(get_engine()) as session:
        row = _incident_row(session, incident_id)
        incident = Incident.model_validate(row.data)
        events = [
            Event.model_validate(data)
            for data in session.scalars(
                select(EventRow.data)
                .join(
                    IncidentEventRow,
                    (EventRow.upload_id == IncidentEventRow.upload_id)
                    & (EventRow.event_id == IncidentEventRow.event_id),
                )
                .where(IncidentEventRow.incident_id == incident_id)
            )
        ]
    # The engine's response.toml: the same internal networks C5 uses to pick targets.
    facts = key_facts(incident, events, response.config)
    return IncidentKeyFacts.model_validate(asdict(facts))


@router.get("/incidents/{incident_id}/events/{event_id}/original", response_model=OriginalRecord)
def original_record(incident_id: str, event_id: str) -> OriginalRecord:
    """The uploaded line an event came from (FR-05). It is the raw record, not masked."""
    with Session(get_engine()) as session:
        row = _incident_row(session, incident_id)
        linked = session.get(IncidentEventRow, (incident_id, event_id))
        if linked is None:
            raise ApiException(
                404, ErrorCode.NOT_FOUND, f"Event {event_id} is not in incident {incident_id}."
            )
        data = session.scalar(
            select(EventRow.data).where(
                EventRow.upload_id == row.upload_id, EventRow.event_id == event_id
            )
        )
    event = Event.model_validate(data)
    path = get_settings().upload_dir / row.upload_id
    try:
        line = read_original(path, event.provenance.record_ref)
    except ValueError:
        # A fixture event's record_ref is its own ID, not a line of the uploaded file.
        raise ApiException(
            404,
            ErrorCode.ORIGINAL_NOT_AVAILABLE,
            "This event's record reference does not point at a line of the uploaded file.",
        ) from None
    except (OSError, LookupError):
        raise ApiException(
            404,
            ErrorCode.ORIGINAL_NOT_AVAILABLE,
            "The uploaded file for this event is no longer stored.",
        ) from None
    return OriginalRecord(
        event_id=event.event_id,
        record_ref=event.provenance.record_ref,
        source_file=event.provenance.source_file,
        line=line,
    )


@router.get("/incidents/{incident_id}/report", response_model=AnalysisReport)
def incident_report(incident_id: str) -> JSONResponse:
    """The incident's latest valid AI report, un-masked for the analyst's screen (C2-D7).

    The report is stored masked (AI1, migration 0006); only this answer carries real host, user
    and IP values, and the un-masked copy is never stored. 404 report_not_available until the
    analysis job (C1) has stored a valid report for the incident.

    When the report names a token (host-01 ...) that its package's stored masking map does not
    know, the token stays as it is and the answer carries `X-ICD-Report-Masked: 1` (C4-D1), so the
    panel can say that some names are shown as tokens.
    """
    engine = get_engine()
    with Session(engine) as session:
        _incident_row(session, incident_id)
    report = latest_report(engine, incident_id)
    if report is None:
        raise ApiException(
            404, ErrorCode.REPORT_NOT_AVAILABLE, "No AI report is stored for this incident yet."
        )
    masking_map = load_masking_map(engine, report.evidence_package_id, report.incident_id)
    shown = unmask_report(report, masking_map)
    body = shown.model_dump(mode="json")
    headers = {REPORT_MASKED_HEADER: "1"} if _still_masked(shown) else None
    return JSONResponse(body, headers=headers)


REPORT_MASKED_HEADER = "X-ICD-Report-Masked"


def _still_masked(report: AnalysisReport) -> bool:
    """True when a text field still holds a masking token after un-masking."""
    texts = [report.summary, report.attack_type or "", report.uncertainty,
             report.impact or "", report.risk_justification or "",
             *(s.description for s in report.sequence or []),
             *(f.statement for f in report.findings),
             *(report.weaknesses or []), *report.recommendations]  # fmt: skip
    return any(MASKED_TOKEN.search(text) for text in texts)


@router.get("/incidents/{incident_id}/audit", response_model=AuditTrail)
def incident_audit(incident_id: str, response: EngineDep) -> AuditTrail:
    with Session(get_engine()) as session:
        _incident_row(session, incident_id)
    return AuditTrail(items=response.audit_trail(incident_id))


@router.get("/response-windows/{incident_id}", response_model=ResponseWindow)
def response_window(incident_id: str, response: EngineDep) -> JSONResponse:
    view = response.window_of(incident_id)
    if view is None:
        raise ApiException(
            404, ErrorCode.NOT_FOUND, f"Incident {incident_id} has no response window."
        )
    # C5's own JSON, with millisecond times as spec section 7 asks (the model drops ".000").
    body = view.as_json()
    ResponseWindow.model_validate(body)
    return JSONResponse(body)


@router.get("/incidents/{incident_id}/containments", response_model=ContainmentList)
def incident_containments(incident_id: str, response: EngineDep) -> ContainmentList:
    """Simulated IP blocks the incident started or extended, with their planned end (P2)."""
    with Session(get_engine()) as session:
        _incident_row(session, incident_id)
    return ContainmentList(
        items=[
            SimulatedContainment.model_validate(asdict(c))
            for c in response.containments_of(incident_id)
        ]
    )


@router.get("/scenarios", response_model=ScenarioCatalogue)
def scenario_catalogue(response: EngineDep) -> ScenarioCatalogue:
    """P6: the simulated catalogue v0 with impact and how each scenario is reverted (display)."""
    meta = load_scenario_meta()
    return ScenarioCatalogue(
        config_version=response.config.config_version,
        meta_version=meta.config_version,
        items=[
            ScenarioItem(
                scenario_id=scenario.scenario_id,
                title=scenario.title,
                automatic=scenario.automatic,
                needs=sorted(scenario.needs),
                impact=meta.scenarios[scenario.scenario_id].impact,
                reversible=meta.scenarios[scenario.scenario_id].reversible,
                revert=meta.scenarios[scenario.scenario_id].revert,
            )
            for scenario in sorted(response.config.scenarios.values(), key=lambda s: s.scenario_id)
        ],
    )


RECENT_LIMIT = 200


@router.get("/decisions/recent", response_model=RecentDecisionList)
def recent_decisions(
    response: EngineDep, hours: Annotated[int, Query(ge=1, le=168)] = 72
) -> RecentDecisionList:
    """P6: analyst decisions and system selections of the last hours, newest first (audit)."""
    until = response.clock.now()
    since = until - timedelta(hours=hours)
    with Session(get_engine()) as session:
        rows = session.scalars(
            select(AuditRow)
            .where(
                AuditRow.event_type.in_(
                    [AuditEventType.DECISION_RECORDED.value, AuditEventType.SCENARIO_SELECTED.value]
                ),
                AuditRow.occurred_at >= since,
                AuditRow.occurred_at <= until,
            )
            .order_by(AuditRow.seq.desc())
            .limit(RECENT_LIMIT)
        ).all()
    items = []
    for row in rows:
        details = row.details or {}
        system = row.event_type == AuditEventType.SCENARIO_SELECTED.value
        items.append(
            RecentDecision(
                record_id=row.record_id,
                incident_id=row.incident_id,
                occurred_at=row.occurred_at,
                by="system" if system else "analyst",
                actor=row.actor,
                actor_role=row.actor_role,
                decision="system_selection" if system else details.get("decision"),
                scenario_id=details.get("scenario_id"),
                comment=None if system else details.get("comment"),
            )
        )
    return RecentDecisionList(hours=hours, since=since, until=until, items=items)


# ---- decisions -------------------------------------------------------------------------------


def dev_identity() -> tuple[str, UserRole] | None:
    """The development identity until login exists (S8-D4), or None."""
    user = os.environ.get("ICD_DEV_USER", "").strip()
    role = os.environ.get("ICD_DEV_ROLE", "").strip()
    if not user or role not in {r.value for r in UserRole}:
        return None
    return user, UserRole(role)


@router.get("/me", response_model=CurrentUser)
def current_user() -> CurrentUser:
    """Who the API acts as, so the dashboard can apply its role rules (S8-D9). The dashboard
    only hides or explains with it; every permission that exists is checked on the server."""
    identity = dev_identity()
    if identity is None:
        raise ApiException(
            401,
            ErrorCode.NOT_AUTHENTICATED,
            "No signed-in user. Login comes with T2-15; for local development set "
            "ICD_DEV_USER and ICD_DEV_ROLE.",
        )
    user, role = identity
    return CurrentUser(user=user, role=role)


# ---- notifications (S8-D8) -------------------------------------------------------------------


@router.get("/notifications", response_model=NotificationList)
def notifications(
    after: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotificationList:
    """C5's notification.sent audit records of every incident, newest first (spec T03, T09,
    T11). A read of C5's audit table only. With `after`, only records written after that one;
    an unknown `after` (for example after a database reset) is ignored."""
    with Session(get_engine()) as session:
        query = select(AuditRow).where(AuditRow.event_type == AuditEventType.NOTIFICATION_SENT)
        if after is not None:
            seen = session.scalar(select(AuditRow.seq).where(AuditRow.record_id == after))
            if seen is not None:
                query = query.where(AuditRow.seq > seen)
        rows = session.scalars(query.order_by(AuditRow.seq.desc()).limit(limit))
        items = [
            AuditRecord(
                record_id=row.record_id,
                occurred_at=row.occurred_at,
                event_type=row.event_type,
                actor=row.actor,
                actor_role=row.actor_role,
                incident_id=row.incident_id,
                result=row.result,
                simulated=row.simulated,
                details=row.details,
            )
            for row in rows
        ]
    return NotificationList(items=items)


# How a refusal of C5's engine reads over HTTP. WRONG_STATE is split by whether a decision exists.
_REFUSALS = {
    RefusalReason.NOT_AUTHORIZED: (403, ErrorCode.NOT_AUTHORIZED),
    RefusalReason.UNKNOWN_INCIDENT: (404, ErrorCode.NOT_FOUND),
    RefusalReason.WINDOW_EXPIRED: (409, ErrorCode.WINDOW_EXPIRED),
    RefusalReason.WINDOW_MISMATCH: (409, ErrorCode.WINDOW_MISMATCH),
    RefusalReason.WINDOW_OPEN: (409, ErrorCode.WINDOW_OPEN),
    RefusalReason.NO_RECOMMENDATION: (422, ErrorCode.VALIDATION_ERROR),
    RefusalReason.SCENARIO_MISMATCH: (422, ErrorCode.VALIDATION_ERROR),
    RefusalReason.SCENARIO_REQUIRED: (422, ErrorCode.VALIDATION_ERROR),
    RefusalReason.REQUIRED_DATA_MISSING: (422, ErrorCode.VALIDATION_ERROR),
    RefusalReason.COMMENT_REQUIRED: (422, ErrorCode.VALIDATION_ERROR),
}


def _latest_decision(response: ResponseEngine, incident_id: str) -> DecisionRecord | None:
    trail = response.audit_trail(incident_id)
    recorded = [r for r in trail if r.event_type == AuditEventType.DECISION_RECORDED]
    if not recorded:
        return None
    record = recorded[-1]
    details = record.details
    actions = [
        a
        for a in response.actions_of(incident_id)
        if a.decided_at is not None and a.decided_at == record.occurred_at
    ]
    status = response.status_of(incident_id)
    return DecisionRecord(
        incident_id=incident_id,
        window_id=details.get("window_id"),
        decision=details["decision"],
        scenario_id=details.get("scenario_id"),
        comment=details.get("comment"),
        decided_by=record.actor,
        decided_at=record.occurred_at,
        incident_status=status,
        action=actions[-1] if actions else None,
    )


@router.get("/incidents/{incident_id}/decision", response_model=DecisionRecord)
def get_decision(incident_id: str, response: EngineDep) -> DecisionRecord:
    with Session(get_engine()) as session:
        _incident_row(session, incident_id)
    decision = _latest_decision(response, incident_id)
    if decision is None:
        raise ApiException(
            404, ErrorCode.NOT_FOUND, f"No decision is recorded for incident {incident_id}."
        )
    return decision


@router.post("/incidents/{incident_id}/decisions", status_code=201, response_model=DecisionRecord)
def post_decision(incident_id: str, body: DecisionRequest, response: EngineDep) -> DecisionRecord:
    with Session(get_engine()) as session:
        _incident_row(session, incident_id)
    identity = dev_identity()
    if identity is None:
        raise ApiException(
            403,
            ErrorCode.NOT_AUTHORIZED,
            "No signed-in user. Login comes with T2-15; for local development set "
            "ICD_DEV_USER and ICD_DEV_ROLE.",
        )
    actor, role = identity
    if body.decision.value == "reject" and body.scenario_id is not None:
        raise ApiException(422, ErrorCode.VALIDATION_ERROR, "A reject takes no scenario_id.")
    try:
        response.decide(
            incident_id,
            EngineDecision(body.decision.value),
            actor=actor,
            role=role,
            scenario_id=body.scenario_id,
            comment=body.comment,
            window_id=body.window_id,
        )
    except DecisionRefused as refused:
        if refused.reason == RefusalReason.WRONG_STATE:
            decided = _latest_decision(response, incident_id) is not None
            status, code = (
                409,
                (ErrorCode.ALREADY_DECIDED if decided else ErrorCode.NOT_AWAITING_DECISION),
            )
        else:
            status, code = _REFUSALS.get(refused.reason, (409, ErrorCode.VALIDATION_ERROR))
        raise ApiException(
            status, code, refused.message[:1].upper() + refused.message[1:] + "."
        ) from None
    except TransitionRefused:
        raise ApiException(
            409, ErrorCode.NOT_AWAITING_DECISION, "The incident is not awaiting a decision."
        ) from None
    decision = _latest_decision(response, incident_id)
    assert decision is not None
    return decision


# ---- WebSocket: response-window events for the countdown (spec section 7, S8-D3) -----------

# How often the server reads the window. The countdown itself runs from deadline_at and
# server_time, so this only sets how soon a decision or an expiry reaches the page.
POLL_SECONDS = 0.5


def _window_events(previous: WindowView | None, current: WindowView | None) -> list[dict]:
    """The response_window.* events between two reads of the same incident's latest window."""
    if current is None:
        return []
    now = current.as_json()
    base = {"incident_id": now["incident_id"], "window_id": now["window_id"]}
    fresh = previous is None or previous.window_id != current.window_id
    events = []
    if current.status == "open" and (fresh or previous.status != "open"):
        events.append(
            {
                "type": "response_window.opened",
                **base,
                "started_at": now["started_at"],
                "deadline_at": now["deadline_at"],
                "server_time": now["server_time"],
                "recommended_scenario_id": now["recommended_scenario_id"],
            }
        )
    elif current.status != "open" and not fresh and previous.status == "open":
        events.append(
            {"type": f"response_window.{current.status}", **base, "server_time": now["server_time"]}
        )
    return events


@router.websocket("/ws/response-windows")
async def window_socket(
    websocket: WebSocket,
    response: EngineDep,
    incident_id: Annotated[str, Query(min_length=1, max_length=128)],
) -> None:
    await websocket.accept()
    # A window already closed when the page connects is read over REST, not replayed here.
    previous = await run_in_threadpool(response.window_of, incident_id)
    if previous is not None and previous.status == "open":
        for event in _window_events(None, previous):
            await websocket.send_json(event)
    try:
        while True:
            try:
                # Waits POLL_SECONDS, and notices at once when the page goes away.
                await asyncio.wait_for(websocket.receive_text(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
            current = await run_in_threadpool(response.window_of, incident_id)
            for event in _window_events(previous, current):
                await websocket.send_json(event)
            previous = current or previous
    except WebSocketDisconnect:
        return


# ---- re-run the AI analysis (C1, decision F8) --------------------------------------------------


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = Field(
        default=False,
        description="Skip the report cache and call the model again (AI1 step 11).",
    )


@router.post("/incidents/{incident_id}/analysis", status_code=202, response_model=JobAccepted)
def queue_incident_analysis(
    incident_id: str, http_response: Response, body: AnalysisRequest | None = None
) -> JobAccepted:
    """Queue an AI analysis of a stored incident. The ingest job already queues one for every
    incident; this is for a re-run (for example after the model became reachable again).
    An analysis already queued or running for the incident is returned instead of a new one."""
    engine = get_engine()
    with Session(engine) as session:
        _incident_row(session, incident_id)
    job, _ = queue_analysis(
        engine,
        incident_id,
        force=bool(body and body.force),
        now=utcnow(),
        max_attempts=get_settings().job_max_attempts,
    )
    status_url = f"/jobs/{job.job_id}"
    http_response.headers["Location"] = status_url
    return JobAccepted(job_id=job.job_id, status_url=status_url)
