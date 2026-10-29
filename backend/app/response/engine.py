"""Response engine v0 (C5 Week 2): freeze, server-held deadline, decisions, expiry, simulated
execution and audit, on PostgreSQL (response spec sections 3 to 11).

Rule TX (spec section 1): every step writes its transition, its side effects and its audit
records in one database transaction. A refused step changes nothing and is audited on its own.
All times come from the engine's clock: the database clock in the running system, a fake clock in
tests (decision D4). Every action is simulated; nothing here can reach a real host.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.contracts import (
    ActionState,
    ActionTrigger,
    AuditEventType,
    AuditRecord,
    AuditResult,
    Event,
    Incident,
    IncidentStatus,
    ResponseAction,
    ScenarioId,
    UserRole,
)
from app.contracts.audit import SIMULATED_EVENT_TYPES
from app.response.catalogue import lookup
from app.response.clock import Clock
from app.response.config import ResponseConfig, load_response_config
from app.response.executor import (
    SIMULATED_LABEL,
    FailureRule,
    MissingTarget,
    decide,
    execute,
    never_fail,
    propose,
)
from app.response.freeze import NoFreezeReason, check_freeze, report_valid
from app.response.lifecycle import Transition, TransitionRefused, Trigger, transition_for
from app.response.models import (
    AuditRow,
    IncidentLifecycleRow,
    ResponseActionRow,
    ResponseWindowRow,
    StatusHistoryRow,
)
from app.response.targets import Targets, find_targets

SYSTEM = "system"
Details = dict[str, str | int | float | bool | None]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DecisionType(StrEnum):
    """The analyst's options (spec section 8, FR-34) plus T16 (decision D12)."""

    APPROVE = "approve"
    REJECT = "reject"
    SELECT = "select"
    NO_ACTION = "no_action"


class RefusalReason(StrEnum):
    NOT_AUTHORIZED = "not_authorized"
    UNKNOWN_INCIDENT = "unknown_incident"
    WRONG_STATE = "wrong_state"
    WINDOW_EXPIRED = "window_expired"
    WINDOW_MISMATCH = "window_mismatch"
    WINDOW_OPEN = "window_open"
    NO_RECOMMENDATION = "no_recommendation"
    SCENARIO_MISMATCH = "scenario_mismatch"
    SCENARIO_REQUIRED = "scenario_required"
    REQUIRED_DATA_MISSING = "required_data_missing"
    COMMENT_REQUIRED = "comment_required"


HTTP_STATUS = {
    RefusalReason.NOT_AUTHORIZED: 403,
    RefusalReason.UNKNOWN_INCIDENT: 404,
    RefusalReason.SCENARIO_REQUIRED: 422,
    RefusalReason.REQUIRED_DATA_MISSING: 422,
    RefusalReason.COMMENT_REQUIRED: 422,
}


class DecisionRefused(Exception):
    """The decision was not recorded; decision.refused is in the audit trail."""

    def __init__(self, reason: RefusalReason, message: str):
        self.reason, self.message = reason, message
        self.http_status = HTTP_STATUS.get(reason, 409)
        super().__init__(f"{reason.value}: {message}")


@dataclass(frozen=True)
class WindowView:
    """What C4 reads for the countdown (spec section 7)."""

    incident_id: str
    window_id: str
    status: str
    started_at: datetime
    deadline_at: datetime
    server_time: datetime
    recommended_scenario_id: str | None

    def as_json(self) -> dict[str, str | None]:
        return {
            "incident_id": self.incident_id,
            "window_id": self.window_id,
            "status": self.status,
            "started_at": _iso(self.started_at),
            "deadline_at": _iso(self.deadline_at),
            "server_time": _iso(self.server_time),
            "recommended_scenario_id": self.recommended_scenario_id,
        }


@dataclass(frozen=True)
class AnalysisOutcome:
    status: IncidentStatus
    froze: bool
    reasons: tuple[NoFreezeReason, ...]
    recommended_scenario_id: ScenarioId | None
    window: WindowView | None


@dataclass(frozen=True)
class DecisionOutcome:
    status: IncidentStatus
    decision: DecisionType
    action: ResponseAction | None


class ExpiryResult(StrEnum):
    SELECTED = "selected"
    NO_MATCH = "no_match"
    DUPLICATE_IGNORED = "duplicate_ignored"
    NOT_DUE = "not_due"


@dataclass(frozen=True)
class ExpiryOutcome:
    window_id: str
    result: ExpiryResult
    status: IncidentStatus | None
    action: ResponseAction | None


class _Refuse(Exception):
    def __init__(self, reason: RefusalReason, message: str):
        self.reason, self.message = reason, message


class ResponseEngine:
    def __init__(
        self,
        engine: Engine,
        clock: Clock,
        config: ResponseConfig | None = None,
        failure_rule: FailureRule = never_fail,
        ids: Callable[[str], str] = new_id,
    ):
        self.engine, self.clock = engine, clock
        self.config = config or load_response_config()
        self.failure_rule, self.ids = failure_rule, ids

    # ---- audit and transitions -------------------------------------------------------------

    def _audit(
        self,
        session: Session,
        now: datetime,
        event_type: AuditEventType,
        incident_id: str | None,
        details: Details,
        *,
        actor: str = SYSTEM,
        role: UserRole | None = None,
        result: AuditResult = AuditResult.SUCCESS,
    ) -> None:
        """Validate against the AuditRecord contract, then append (C-14, NFR-SF-07)."""
        record = AuditRecord(
            record_id=self.ids("aud"),
            occurred_at=now,
            event_type=event_type,
            actor=actor,
            actor_role=role,
            incident_id=incident_id,
            result=result,
            simulated=event_type in SIMULATED_EVENT_TYPES,
            details=details,
        )
        session.add(
            AuditRow(
                record_id=record.record_id,
                occurred_at=record.occurred_at,
                event_type=record.event_type.value,
                actor=record.actor,
                actor_role=record.actor_role.value if record.actor_role else None,
                incident_id=record.incident_id,
                result=record.result.value,
                simulated=record.simulated,
                details=dict(record.details),
            )
        )
        session.flush()

    def _move(
        self,
        session: Session,
        row: IncidentLifecycleRow,
        trigger: Trigger,
        now: datetime,
        cause: str,
        *,
        actor: str = SYSTEM,
        role: UserRole | None = None,
        details: Details | None = None,
    ) -> Transition:
        """Apply one transition of the table, with its history row and audit record."""
        previous = IncidentStatus(row.status)
        transition = transition_for(previous, trigger)
        row.status = transition.target.value
        row.updated_at = now
        session.add(
            StatusHistoryRow(
                incident_id=row.incident_id,
                transition_id=transition.transition_id,
                previous_status=previous.value,
                new_status=transition.target.value,
                actor=actor,
                cause=cause,
                changed_at=now,
            )
        )
        self._audit(
            session,
            now,
            AuditEventType.STATUS_CHANGED,
            row.incident_id,
            {
                "transition_id": transition.transition_id,
                "previous_status": previous.value,
                "new_status": transition.target.value,
                "cause": cause,
                **(details or {}),
            },
            actor=actor,
            role=role,
        )
        return transition

    def _refused_transition(self, incident_id: str, refused: TransitionRefused, actor: str, role):
        """T15: audit the refusal in its own transaction; the state did not change."""
        with Session(self.engine) as session, session.begin():
            self._audit(
                session,
                self.clock.now(),
                AuditEventType.TRANSITION_REFUSED,
                incident_id,
                {
                    "transition_id": "T15",
                    "from_status": refused.source.value if refused.source else None,
                    "trigger": refused.trigger.value,
                },
                actor=actor,
                role=role,
                result=AuditResult.REFUSED,
            )

    def _lifecycle(self, session: Session, incident_id: str) -> IncidentLifecycleRow | None:
        return session.scalars(
            select(IncidentLifecycleRow)
            .where(IncidentLifecycleRow.incident_id == incident_id)
            .with_for_update()
        ).first()

    def _open_window(self, session: Session, incident_id: str) -> ResponseWindowRow | None:
        return session.scalars(
            select(ResponseWindowRow)
            .where(ResponseWindowRow.incident_id == incident_id, ResponseWindowRow.status == "open")
            .with_for_update()
        ).first()

    @staticmethod
    def _targets(row: IncidentLifecycleRow) -> Targets:
        return Targets(row.target_host, row.target_source_ip, row.target_account)

    # ---- T01, T02, T05: creation and analysis ----------------------------------------------

    def register(self, incident: Incident) -> IncidentStatus:
        """T01: start tracking an incident that C3's correlation created."""
        try:
            with Session(self.engine) as session, session.begin():
                now = self.clock.now()
                existing = self._lifecycle(session, incident.incident_id)
                if existing is not None:
                    raise TransitionRefused(
                        IncidentStatus(existing.status), Trigger.INCIDENT_CREATED
                    )
                transition = transition_for(None, Trigger.INCIDENT_CREATED)
                row = IncidentLifecycleRow(
                    incident_id=incident.incident_id,
                    status=transition.target.value,
                    isolated=False,
                    incident_type=incident.incident_type,
                    risk_level=incident.risk.level.value if incident.risk else None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                session.add(
                    StatusHistoryRow(
                        incident_id=row.incident_id,
                        transition_id=transition.transition_id,
                        previous_status=None,
                        new_status=transition.target.value,
                        actor=SYSTEM,
                        cause="incident created by correlation",
                        changed_at=now,
                    )
                )
                self._audit(
                    session,
                    now,
                    AuditEventType.STATUS_CHANGED,
                    row.incident_id,
                    {
                        "transition_id": transition.transition_id,
                        "previous_status": None,
                        "new_status": transition.target.value,
                        "cause": "incident created by correlation",
                    },
                )
                return transition.target
        except TransitionRefused as refused:
            self._refused_transition(incident.incident_id, refused, SYSTEM, None)
            raise

    def _simple(self, incident_id: str, trigger: Trigger, cause: str) -> IncidentStatus:
        try:
            with Session(self.engine) as session, session.begin():
                row = self._lifecycle(session, incident_id)
                if row is None:
                    raise KeyError(f"unknown incident {incident_id}")
                return self._move(session, row, trigger, self.clock.now(), cause).target
        except TransitionRefused as refused:
            self._refused_transition(incident_id, refused, SYSTEM, None)
            raise

    def start_analysis(self, incident_id: str) -> IncidentStatus:
        """T02: the analysis job started."""
        return self._simple(incident_id, Trigger.ANALYSIS_STARTED, "analysis started")

    def record_analysis(self, incident: Incident, events: Iterable[Event]) -> AnalysisOutcome:
        """After an analysis: T05 if it is not valid, else T03 (freeze) or T04 (no timer)."""
        try:
            return self._record_analysis(incident, list(events))
        except TransitionRefused as refused:
            self._refused_transition(incident.incident_id, refused, SYSTEM, None)
            raise

    def _record_analysis(self, incident: Incident, events: list[Event]) -> AnalysisOutcome:
        with Session(self.engine) as session, session.begin():
            now = self.clock.now()
            row = self._lifecycle(session, incident.incident_id)
            if row is None:
                raise KeyError(f"unknown incident {incident.incident_id}")

            if not report_valid(incident):  # OD-09: a failed analysis never freezes
                self._move(session, row, Trigger.ANALYSIS_FAILED, now, "analysis failed")
                self._audit(
                    session,
                    now,
                    AuditEventType.ANALYSIS_FAILED,
                    row.incident_id,
                    {"attempt": incident.analysis_attempts, "analysis_status": "failed"},
                    result=AuditResult.FAILURE,
                )
                return AnalysisOutcome(
                    IncidentStatus(row.status),
                    False,
                    (NoFreezeReason.ANALYSIS_NOT_VALID,),
                    None,
                    None,
                )

            targets = find_targets(incident, events, self.config)
            window_open = self._open_window(session, row.incident_id) is not None
            check = check_freeze(incident, targets, window_open=window_open, config=self.config)
            recommendation = lookup(
                targets,
                incident_type=incident.incident_type,
                confidence=incident.confidence,
                config=self.config,
            ).scenario_id
            row.target_host, row.target_source_ip = targets.host, targets.source_ip
            row.target_account = targets.account
            row.incident_type = incident.incident_type
            row.risk_level = incident.risk.level.value if incident.risk else None
            row.confidence = incident.confidence
            row.recommended_scenario_id = recommendation.value if recommendation else None
            gate: Details = {
                "freeze": check.freeze,
                "reasons": ",".join(r.value for r in check.reasons),
                "risk_level": row.risk_level,
                "confidence": incident.confidence,
                "recommended_scenario_id": row.recommended_scenario_id,
            }

            if not check.freeze:
                self._move(
                    session,
                    row,
                    Trigger.ANALYSED_NO_FREEZE,
                    now,
                    "analysed, no freeze",
                    details=gate,
                )
                return AnalysisOutcome(
                    IncidentStatus(row.status), False, check.reasons, recommendation, None
                )

            window = ResponseWindowRow(
                window_id=self.ids("win"),
                incident_id=row.incident_id,
                status="open",
                started_at=now,
                deadline_at=now + timedelta(seconds=self.config.window_seconds),
                recommended_scenario_id=row.recommended_scenario_id,
            )
            session.add(window)
            session.flush()
            self._move(session, row, Trigger.FREEZE_STARTED, now, "freeze started", details=gate)
            row.isolated = True
            self._audit(
                session,
                now,
                AuditEventType.ACTION_SIMULATED,
                row.incident_id,
                {
                    "action": "isolate",
                    "host": targets.host,
                    "window_id": window.window_id,
                    "label": SIMULATED_LABEL,
                },
            )
            self._audit(
                session,
                now,
                AuditEventType.RESPONSE_WINDOW_OPENED,
                row.incident_id,
                {
                    "window_id": window.window_id,
                    "started_at": _iso(window.started_at),
                    "deadline_at": _iso(window.deadline_at),
                    "recommended_scenario_id": window.recommended_scenario_id,
                },
            )
            self._audit(
                session,
                now,
                AuditEventType.NOTIFICATION_SENT,
                row.incident_id,
                {"recipients": "soc_analyst,soc_manager", "reason": "freeze_started"},
            )
            return AnalysisOutcome(
                IncidentStatus(row.status), True, (), recommendation, self._view(window, now)
            )

    # ---- decisions: T06, T07, T12, T16 -----------------------------------------------------

    def decide(
        self,
        incident_id: str,
        decision: DecisionType,
        *,
        actor: str,
        role: UserRole,
        scenario_id: ScenarioId | None = None,
        comment: str | None = None,
        window_id: str | None = None,
    ) -> DecisionOutcome:
        """Record an analyst decision (FR-28, FR-34), then run its simulated action, if any."""
        details: Details = {
            "decision": decision.value,
            "scenario_id": scenario_id.value if scenario_id else None,
            "window_id": window_id,
        }
        try:
            with Session(self.engine) as session, session.begin():
                outcome, action_id = self._decide(
                    session, incident_id, decision, actor, role, scenario_id, comment, window_id
                )
        except _Refuse as refusal:
            with Session(self.engine) as session, session.begin():
                self._audit(
                    session,
                    self.clock.now(),
                    AuditEventType.DECISION_REFUSED,
                    incident_id,
                    details | {"reason": refusal.reason.value},
                    actor=actor,
                    role=role,
                    result=AuditResult.REFUSED,
                )
            raise DecisionRefused(refusal.reason, refusal.message) from None
        except TransitionRefused as refused:
            self._refused_transition(incident_id, refused, actor, role)
            raise
        if action_id is None:
            return outcome
        status, action = self._run_action(action_id)
        return DecisionOutcome(status, decision, action)

    def _decide(
        self,
        session: Session,
        incident_id: str,
        decision: DecisionType,
        actor: str,
        role: UserRole,
        scenario_id: ScenarioId | None,
        comment: str | None,
        window_id: str | None,
    ) -> tuple[DecisionOutcome, str | None]:
        if role != UserRole.SOC_ANALYST:  # D1.2, FR-39; SOC Manager reviews only (OD-24)
            raise _Refuse(RefusalReason.NOT_AUTHORIZED, "only a SOC Analyst may decide")
        now = self.clock.now()
        row = self._lifecycle(session, incident_id)
        if row is None:
            raise _Refuse(RefusalReason.UNKNOWN_INCIDENT, f"unknown incident {incident_id}")
        status = IncidentStatus(row.status)
        allowed = {
            IncidentStatus.AWAITING_HUMAN_DECISION: set(DecisionType),
            IncidentStatus.ESCALATED: {
                DecisionType.APPROVE,
                DecisionType.SELECT,
                DecisionType.NO_ACTION,
            },
        }
        if decision not in allowed.get(status, set()):
            raise _Refuse(RefusalReason.WRONG_STATE, f"{decision.value} is not open in {status}")

        window = self._open_window(session, incident_id)
        if window_id is not None and (window is None or window.window_id != window_id):
            known = session.get(ResponseWindowRow, window_id)
            if known is not None and known.status == "expired":
                raise _Refuse(RefusalReason.WINDOW_EXPIRED, "the response window expired")
            raise _Refuse(RefusalReason.WINDOW_MISMATCH, "that response window is not open")
        if window is not None and now >= window.deadline_at:  # no grace period (spec case 4)
            raise _Refuse(RefusalReason.WINDOW_EXPIRED, "the response window expired")

        comment = comment.strip() if comment and comment.strip() else None
        action: ResponseAction | None = None
        if decision in (DecisionType.APPROVE, DecisionType.SELECT):
            recommended = row.recommended_scenario_id
            if decision == DecisionType.APPROVE:
                if recommended is None:
                    raise _Refuse(RefusalReason.NO_RECOMMENDATION, "no scenario is recommended")
                if scenario_id is not None and scenario_id.value != recommended:
                    raise _Refuse(RefusalReason.SCENARIO_MISMATCH, "not the recommended scenario")
                scenario_id = ScenarioId(recommended)
            elif scenario_id is None:
                raise _Refuse(RefusalReason.SCENARIO_REQUIRED, "select needs a scenario_id")
            try:
                action = propose(
                    action_id=self.ids("act"),
                    incident_id=incident_id,
                    scenario_id=scenario_id,
                    targets=self._targets(row),
                    isolated=row.isolated,
                    now=now,
                    window_id=window.window_id if window else None,
                )
            except MissingTarget as missing:
                raise _Refuse(RefusalReason.REQUIRED_DATA_MISSING, str(missing)) from None
            action = decide(
                action,
                trigger=ActionTrigger.ANALYST_DECISION,
                decided_by=actor,
                now=now,
                comment=comment,
            )
        if decision == DecisionType.NO_ACTION:
            if comment is None:
                raise _Refuse(RefusalReason.COMMENT_REQUIRED, "no_action needs a comment")
            if window is not None:
                raise _Refuse(RefusalReason.WINDOW_OPEN, "decide within the open window instead")

        if window is not None:
            closed = session.execute(
                update(ResponseWindowRow)
                .where(
                    ResponseWindowRow.window_id == window.window_id,
                    ResponseWindowRow.status == "open",
                    ResponseWindowRow.deadline_at > now,
                )
                .values(status="decided", closed_at=now)
            ).rowcount
            if closed != 1:
                raise _Refuse(RefusalReason.WINDOW_EXPIRED, "the response window expired")

        self._audit(
            session,
            now,
            AuditEventType.DECISION_RECORDED,
            incident_id,
            {
                "decision": decision.value,
                "scenario_id": scenario_id.value if scenario_id else None,
                "window_id": window.window_id if window else None,
                "comment": comment,
            },
            actor=actor,
            role=role,
        )
        trigger = {
            DecisionType.APPROVE: Trigger.ANALYST_DECISION,
            DecisionType.SELECT: Trigger.ANALYST_DECISION,
            DecisionType.REJECT: Trigger.ANALYST_REJECT,
            DecisionType.NO_ACTION: Trigger.NO_RESPONSE_NEEDED,
        }[decision]
        self._move(
            session,
            row,
            trigger,
            now,
            f"analyst decision: {decision.value}",
            actor=actor,
            role=role,
        )
        if decision == DecisionType.REJECT and window is not None and row.isolated:
            row.isolated = False
            self._audit(
                session,
                now,
                AuditEventType.ISOLATION_RELEASED,
                incident_id,
                {"host": row.target_host, "window_id": window.window_id, "label": SIMULATED_LABEL},
                actor=actor,
                role=role,
            )
        if action is not None:
            self._store_action(session, action, now)
        outcome = DecisionOutcome(IncidentStatus(row.status), decision, action)
        return outcome, action.action_id if action else None

    # ---- expiry: T08, T09 ------------------------------------------------------------------

    def due_windows(self) -> list[str]:
        """Open windows whose deadline has passed, oldest deadline first."""
        now = self.clock.now()
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(ResponseWindowRow.window_id)
                    .where(ResponseWindowRow.status == "open", ResponseWindowRow.deadline_at <= now)
                    .order_by(ResponseWindowRow.deadline_at, ResponseWindowRow.window_id)
                )
            )

    def expire_due(self) -> list[ExpiryOutcome]:
        """One pass of the expiry worker. Safe to run twice or from two workers at once."""
        return [self.expire_window(window_id) for window_id in self.due_windows()]

    def run_pending_actions(self) -> list[str]:
        """Simulate approved actions that were never run (a process stopped between the decision
        and the simulation). Returns their IDs. Safe to run twice: each runs exactly once."""
        with Session(self.engine) as session:
            pending = list(
                session.scalars(
                    select(ResponseActionRow.action_id)
                    .where(ResponseActionRow.state == "approved")
                    .order_by(ResponseActionRow.updated_at, ResponseActionRow.action_id)
                )
            )
        for action_id in pending:
            self._run_action(action_id)
        return pending

    def expire_window(self, window_id: str) -> ExpiryOutcome:
        """Close one window exactly once and follow the expiry path (FR-27, FR-44, AS-10)."""
        with Session(self.engine) as session, session.begin():
            now = self.clock.now()
            closed = session.execute(
                update(ResponseWindowRow)
                .where(
                    ResponseWindowRow.window_id == window_id,
                    ResponseWindowRow.status == "open",
                    ResponseWindowRow.deadline_at <= now,
                )
                .values(status="expired", closed_at=now)
                .returning(ResponseWindowRow.incident_id, ResponseWindowRow.deadline_at)
            ).first()
            if closed is None:
                window = session.get(ResponseWindowRow, window_id)
                if window is None:
                    raise KeyError(f"unknown window {window_id}")
                if window.status == "open":
                    return ExpiryOutcome(window_id, ExpiryResult.NOT_DUE, None, None)
                self._audit(
                    session,
                    now,
                    AuditEventType.EXPIRY_DUPLICATE_IGNORED,
                    window.incident_id,
                    {"window_id": window_id, "window_status": window.status},
                    result=AuditResult.IGNORED,
                )
                return ExpiryOutcome(window_id, ExpiryResult.DUPLICATE_IGNORED, None, None)

            incident_id, deadline_at = closed
            row = self._lifecycle(session, incident_id)
            self._audit(
                session,
                now,
                AuditEventType.RESPONSE_WINDOW_EXPIRED,
                incident_id,
                {
                    "window_id": window_id,
                    "deadline_at": _iso(deadline_at),
                    "processed_at": _iso(now),
                    "late_ms": int((now - deadline_at) / timedelta(milliseconds=1)),
                    "statement": "the response window expired without an analyst decision",
                },
            )
            targets = self._targets(row)
            found = lookup(
                targets,
                incident_type=row.incident_type,
                confidence=row.confidence,
                config=self.config,
            )
            inputs: Details = {"window_id": window_id, **found.inputs}
            if found.scenario_id is None:
                self._move(
                    session,
                    row,
                    Trigger.WINDOW_EXPIRED_NO_MATCH,
                    now,
                    "response window expired, no catalogue scenario matches",
                )
                self._audit(session, now, AuditEventType.SCENARIO_NO_MATCH, incident_id, inputs)
                self._audit(
                    session,
                    now,
                    AuditEventType.NOTIFICATION_SENT,
                    incident_id,
                    {"recipients": "soc_manager", "reason": "no_match"},
                )
                return ExpiryOutcome(
                    window_id, ExpiryResult.NO_MATCH, IncidentStatus(row.status), None
                )

            action = decide(
                propose(
                    action_id=self.ids("act"),
                    incident_id=incident_id,
                    scenario_id=found.scenario_id,
                    targets=targets,
                    isolated=row.isolated,
                    now=now,
                    window_id=window_id,
                ),
                trigger=ActionTrigger.WINDOW_EXPIRY,
                decided_by=SYSTEM,
                now=now,
            )
            self._audit(
                session,
                now,
                AuditEventType.SCENARIO_SELECTED,
                incident_id,
                inputs | {"scenario_id": found.scenario_id.value},
            )
            self._move(session, row, Trigger.WINDOW_EXPIRED_MATCH, now, "response window expired")
            self._store_action(session, action, now)
        status, done = self._run_action(action.action_id)
        return ExpiryOutcome(window_id, ExpiryResult.SELECTED, status, done)

    # ---- simulated execution: T10, T11 -----------------------------------------------------

    def _store_action(self, session: Session, action: ResponseAction, now: datetime) -> None:
        session.add(
            ResponseActionRow(
                action_id=action.action_id,
                incident_id=action.incident_id,
                window_id=action.window_id,
                scenario_id=action.scenario_id.value,
                state=action.state.value,
                data=action.model_dump(mode="json"),
                updated_at=now,
            )
        )
        session.flush()

    def _run_action(self, action_id: str) -> tuple[IncidentStatus, ResponseAction]:
        with Session(self.engine) as session, session.begin():
            now = self.clock.now()
            stored = session.get(ResponseActionRow, action_id, with_for_update=True)
            action = ResponseAction.model_validate(stored.data)
            row = self._lifecycle(session, action.incident_id)
            if action.state != ActionState.APPROVED:  # another process already ran it
                return IncidentStatus(row.status), action
            result = execute(action, isolated=row.isolated, now=now, failure_rule=self.failure_rule)
            done = result.action
            stored.state, stored.data, stored.updated_at = (
                done.state.value,
                done.model_dump(mode="json"),
                now,
            )
            row.isolated = result.isolated_after
            actor, role = (SYSTEM, None)
            self._audit(
                session,
                now,
                AuditEventType.ACTION_SIMULATED,
                action.incident_id,
                {
                    "action_id": done.action_id,
                    "scenario_id": done.scenario_id.value,
                    "host": done.target.host,
                    "ip": done.target.ip,
                    "account": done.target.account,
                    "decided_by": done.decided_by,
                    "trigger": done.trigger.value if done.trigger else None,
                    "failure_reason": done.failure_reason,
                    "label": SIMULATED_LABEL,
                },
                actor=actor,
                role=role,
                result=AuditResult.SUCCESS if result.succeeded else AuditResult.FAILURE,
            )
            if result.succeeded:
                self._move(
                    session, row, Trigger.ACTION_SUCCEEDED, now, "simulated action succeeded"
                )
            else:
                self._move(session, row, Trigger.ACTION_FAILED, now, "simulated action failed")
                self._audit(
                    session,
                    now,
                    AuditEventType.NOTIFICATION_SENT,
                    action.incident_id,
                    {"recipients": "soc_analyst,soc_manager", "reason": "simulated_action_failed"},
                )
            return IncidentStatus(row.status), done

    # ---- reads -----------------------------------------------------------------------------

    def _view(self, window: ResponseWindowRow, server_time: datetime) -> WindowView:
        return WindowView(
            incident_id=window.incident_id,
            window_id=window.window_id,
            status=window.status,
            started_at=window.started_at,
            deadline_at=window.deadline_at,
            server_time=server_time,
            recommended_scenario_id=window.recommended_scenario_id,
        )

    def window_of(self, incident_id: str) -> WindowView | None:
        """The incident's latest response window, with the server time, for the countdown."""
        with Session(self.engine) as session:
            window = session.scalars(
                select(ResponseWindowRow)
                .where(ResponseWindowRow.incident_id == incident_id)
                .order_by(ResponseWindowRow.started_at.desc())
                .limit(1)
            ).first()
            return self._view(window, self.clock.now()) if window else None

    def status_of(self, incident_id: str) -> IncidentStatus | None:
        with Session(self.engine) as session:
            row = session.get(IncidentLifecycleRow, incident_id)
            return IncidentStatus(row.status) if row else None

    def isolated(self, incident_id: str) -> bool:
        with Session(self.engine) as session:
            return session.get(IncidentLifecycleRow, incident_id).isolated

    def audit_trail(self, incident_id: str) -> list[AuditRecord]:
        """The incident's audit records in the order they were written."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(AuditRow).where(AuditRow.incident_id == incident_id).order_by(AuditRow.seq)
            )
            return [AuditRecord.model_validate(_record(row)) for row in rows]

    def actions_of(self, incident_id: str) -> list[ResponseAction]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ResponseActionRow)
                .where(ResponseActionRow.incident_id == incident_id)
                .order_by(ResponseActionRow.updated_at, ResponseActionRow.action_id)
            )
            return [ResponseAction.model_validate(row.data) for row in rows]


def _record(row: AuditRow) -> dict[str, Any]:
    return {
        "record_id": row.record_id,
        "occurred_at": row.occurred_at,
        "event_type": row.event_type,
        "actor": row.actor,
        "actor_role": row.actor_role,
        "incident_id": row.incident_id,
        "result": row.result,
        "simulated": row.simulated,
        "details": row.details,
    }
