"""Transition table (response spec section 3, FR-31): every allowed move, and T15 for the rest."""

import pytest

from app.contracts import IncidentStatus
from app.response import TRANSITIONS, TransitionRefused, Trigger, transition_for

S = IncidentStatus

ALLOWED = [
    ("T01", None, Trigger.INCIDENT_CREATED, S.NEW),
    ("T02", S.NEW, Trigger.ANALYSIS_STARTED, S.UNDER_ANALYSIS),
    ("T03", S.UNDER_ANALYSIS, Trigger.FREEZE_STARTED, S.AWAITING_HUMAN_DECISION),
    ("T04", S.UNDER_ANALYSIS, Trigger.ANALYSED_NO_FREEZE, S.AWAITING_HUMAN_DECISION),
    ("T05", S.UNDER_ANALYSIS, Trigger.ANALYSIS_FAILED, S.UNDER_ANALYSIS),
    ("T06", S.AWAITING_HUMAN_DECISION, Trigger.ANALYST_DECISION, S.RESPONSE_IN_PROGRESS),
    ("T07", S.AWAITING_HUMAN_DECISION, Trigger.ANALYST_REJECT, S.AWAITING_HUMAN_DECISION),
    ("T08", S.AWAITING_HUMAN_DECISION, Trigger.WINDOW_EXPIRED_MATCH, S.RESPONSE_IN_PROGRESS),
    ("T09", S.AWAITING_HUMAN_DECISION, Trigger.WINDOW_EXPIRED_NO_MATCH, S.ESCALATED),
    ("T10", S.RESPONSE_IN_PROGRESS, Trigger.ACTION_SUCCEEDED, S.RESOLVED),
    ("T11", S.RESPONSE_IN_PROGRESS, Trigger.ACTION_FAILED, S.ESCALATED),
    ("T12", S.ESCALATED, Trigger.ANALYST_DECISION, S.RESPONSE_IN_PROGRESS),
    ("T13", S.RESOLVED, Trigger.RESOLUTION_CONFIRMED, S.CLOSED),
    ("T14", S.RESOLVED, Trigger.NEW_RELATED_EVENTS, S.UNDER_ANALYSIS),
    ("T16", S.AWAITING_HUMAN_DECISION, Trigger.NO_RESPONSE_NEEDED, S.RESOLVED),
    ("T16", S.ESCALATED, Trigger.NO_RESPONSE_NEEDED, S.RESOLVED),
]


@pytest.mark.parametrize(("tid", "source", "trigger", "target"), ALLOWED)
def test_allowed_transitions(tid, source, trigger, target):
    transition = transition_for(source, trigger)
    assert (transition.transition_id, transition.target) == (tid, target)


def test_the_table_is_exactly_the_spec():
    assert {(t.transition_id, t.source, t.trigger, t.target) for t in TRANSITIONS} == set(ALLOWED)


def test_every_other_pair_is_refused_as_t15():
    allowed = {(source, trigger) for _, source, trigger, _ in ALLOWED}
    refused = 0
    for source in [None, *IncidentStatus]:
        for trigger in Trigger:
            if (source, trigger) in allowed:
                continue
            with pytest.raises(TransitionRefused) as info:
                transition_for(source, trigger)
            assert info.value.transition_id == "T15"
            refused += 1
    assert refused == 8 * len(Trigger) - len(ALLOWED)


@pytest.mark.parametrize(
    ("source", "trigger"),
    [
        (S.CLOSED, Trigger.NEW_RELATED_EVENTS),  # no reopening in the MVP (OD-14)
        (S.NEW, Trigger.FREEZE_STARTED),  # never freeze before an analysis
        (S.RESPONSE_IN_PROGRESS, Trigger.ANALYST_DECISION),  # one decision at a time
        (S.ESCALATED, Trigger.ANALYST_REJECT),  # no window to reject in Escalated
        (S.CLOSED, Trigger.RESOLUTION_CONFIRMED),
    ],
)
def test_examples_of_refused_transitions(source, trigger):
    with pytest.raises(TransitionRefused):
        transition_for(source, trigger)
