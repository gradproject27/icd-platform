"""Evidence groups for the LLM opinion: the same groups C3's risk score uses.

An incident's flagged events are grouped by `(technique, entity)`: technique = the dataset attack
type, or "unknown"; entity = `app.correlation.risk.entity_of`. Both come from C3's code, so a
`GroupOpinion` key always matches a risk group.

`labelled_groups` builds the calibration set (design note 9A.2, step 3): flagged groups are the
positives (truth 1); unflagged events grouped the same way by entity are the negatives (truth 0).
Long runs are cut where two consecutive events are more than `max_gap` apart (C2-D14 uses the
same 60-minute gap for its ground truth), so a calibration group looks like an incident group.
Unlabelled events are never used: their truth is not known.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta

from app.contracts import Event, EventRole, Incident, LabelStatus
from app.correlation.risk import entity_of

UNKNOWN_TECHNIQUE = "unknown"
# Technique slot of a negative calibration group; never a dataset attack type.
NORMAL_TECHNIQUE = "normal"
DEFAULT_MAX_GAP = timedelta(minutes=60)


@dataclass(frozen=True)
class OpinionGroup:
    technique: str
    entity: str
    events: tuple[Event, ...]  # time order, ties by event ID
    incident_id: str | None = None
    truth: int | None = None  # calibration groups only: 1 attack, 0 normal

    @property
    def key(self) -> tuple[str, str]:
        return (self.technique, self.entity)


def _order(event: Event) -> tuple:
    return (event.timestamp, event.event_id)


def technique_of(event: Event) -> str:
    """The technique part of C3's group key (risk.event_strength: attack type or 'unknown')."""
    return event.label.attack_type or UNKNOWN_TECHNIQUE


def incident_groups(incident: Incident, events: Mapping[str, Event]) -> list[OpinionGroup]:
    """The evidence groups of one incident, sorted by key. Only flagged events count."""
    by_key: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for link in incident.events:
        if link.role != EventRole.FLAGGED:
            continue
        event = events.get(link.event_id)
        if event is None:
            raise ValueError(f"{incident.incident_id}: linked event {link.event_id} not given")
        by_key[(technique_of(event), entity_of(event))].append(event)
    return [
        OpinionGroup(technique, entity, tuple(sorted(evs, key=_order)), incident.incident_id)
        for (technique, entity), evs in sorted(by_key.items())
    ]


def _split_runs(events: list[Event], max_gap: timedelta) -> list[list[Event]]:
    runs: list[list[Event]] = []
    for event in sorted(events, key=_order):
        if runs and event.timestamp - runs[-1][-1].timestamp <= max_gap:
            runs[-1].append(event)
        else:
            runs.append([event])
    return runs


def labelled_groups(
    events: Iterable[Event], max_gap: timedelta = DEFAULT_MAX_GAP
) -> list[OpinionGroup]:
    """Calibration groups with their truth, in a fixed order (key, then start time)."""
    by_key: dict[tuple[str, str, int], list[Event]] = defaultdict(list)
    for event in events:
        if event.label.status == LabelStatus.FLAGGED:
            by_key[(technique_of(event), entity_of(event), 1)].append(event)
        elif event.label.status == LabelStatus.UNFLAGGED:
            by_key[(NORMAL_TECHNIQUE, entity_of(event), 0)].append(event)
    groups = []
    for (technique, entity, truth), evs in sorted(by_key.items()):
        for run in _split_runs(evs, max_gap):
            groups.append(OpinionGroup(technique, entity, tuple(run), truth=truth))
    return groups
