"""Incident lifecycle: the transition table of docs/response-workflow-spec.md section 3 (FR-31).

Each transition is (from state, trigger) -> to state, with the spec's ID. Anything not in the
table is refused (T15): the state does not change and the caller audits transition_refused.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.contracts import IncidentStatus

NEW = IncidentStatus.NEW
UNDER_ANALYSIS = IncidentStatus.UNDER_ANALYSIS
AWAITING = IncidentStatus.AWAITING_HUMAN_DECISION
IN_PROGRESS = IncidentStatus.RESPONSE_IN_PROGRESS
ESCALATED = IncidentStatus.ESCALATED
RESOLVED = IncidentStatus.RESOLVED
CLOSED = IncidentStatus.CLOSED


class Trigger(StrEnum):
    """What asks for a transition."""

    INCIDENT_CREATED = "incident_created"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_FAILED = "analysis_failed"
    FREEZE_STARTED = "freeze_started"
    ANALYSED_NO_FREEZE = "analysed_no_freeze"
    ANALYST_DECISION = "analyst_decision"  # approve, or select a scenario
    ANALYST_REJECT = "analyst_reject"  # reject during a freeze; isolation released
    WINDOW_EXPIRED_MATCH = "window_expired_match"
    WINDOW_EXPIRED_NO_MATCH = "window_expired_no_match"
    ACTION_SUCCEEDED = "action_succeeded"
    ACTION_FAILED = "action_failed"
    RESOLUTION_CONFIRMED = "resolution_confirmed"
    NEW_RELATED_EVENTS = "new_related_events"
    NO_RESPONSE_NEEDED = "no_response_needed"  # T16, proposed in the spec


@dataclass(frozen=True)
class Transition:
    transition_id: str
    source: IncidentStatus | None  # None: the incident does not exist yet
    trigger: Trigger
    target: IncidentStatus


TRANSITIONS: tuple[Transition, ...] = (
    Transition("T01", None, Trigger.INCIDENT_CREATED, NEW),
    Transition("T02", NEW, Trigger.ANALYSIS_STARTED, UNDER_ANALYSIS),
    Transition("T03", UNDER_ANALYSIS, Trigger.FREEZE_STARTED, AWAITING),
    Transition("T04", UNDER_ANALYSIS, Trigger.ANALYSED_NO_FREEZE, AWAITING),
    Transition("T05", UNDER_ANALYSIS, Trigger.ANALYSIS_FAILED, UNDER_ANALYSIS),
    Transition("T06", AWAITING, Trigger.ANALYST_DECISION, IN_PROGRESS),
    Transition("T07", AWAITING, Trigger.ANALYST_REJECT, AWAITING),
    Transition("T08", AWAITING, Trigger.WINDOW_EXPIRED_MATCH, IN_PROGRESS),
    Transition("T09", AWAITING, Trigger.WINDOW_EXPIRED_NO_MATCH, ESCALATED),
    Transition("T10", IN_PROGRESS, Trigger.ACTION_SUCCEEDED, RESOLVED),
    Transition("T11", IN_PROGRESS, Trigger.ACTION_FAILED, ESCALATED),
    Transition("T12", ESCALATED, Trigger.ANALYST_DECISION, IN_PROGRESS),
    Transition("T13", RESOLVED, Trigger.RESOLUTION_CONFIRMED, CLOSED),
    Transition("T14", RESOLVED, Trigger.NEW_RELATED_EVENTS, UNDER_ANALYSIS),
    Transition("T16", AWAITING, Trigger.NO_RESPONSE_NEEDED, RESOLVED),
    Transition("T16", ESCALATED, Trigger.NO_RESPONSE_NEEDED, RESOLVED),
)

_TABLE: dict[tuple[IncidentStatus | None, Trigger], Transition] = {
    (t.source, t.trigger): t for t in TRANSITIONS
}


class TransitionRefused(Exception):
    """T15: the transition is not in the table. The state does not change."""

    transition_id = "T15"

    def __init__(self, source: IncidentStatus | None, trigger: Trigger):
        self.source, self.trigger = source, trigger
        name = source.value if source else "none"
        super().__init__(f"no transition from {name} on {trigger.value}")


def transition_for(source: IncidentStatus | None, trigger: Trigger) -> Transition:
    """The allowed transition, or TransitionRefused (T15)."""
    try:
        return _TABLE[(source, trigger)]
    except KeyError:
        raise TransitionRefused(source, trigger) from None
