"""Evidence package builder (C2, T3-06; workflow step 4): Incident + Events -> EvidencePackage.

Rules (team plan W3-D4, decisions C2-D1 to C2-D4):

1. All flagged events of the incident, in time order (ties by event ID), up to 50.
2. The remaining places go to context events (unflagged or unlabelled), nearest in time to a
   flagged event in the package first; ties by time, then event ID. Context is never sampled
   at random, so the same incident always gives the same package (and the same cache key).
3. `truncated` is true exactly when the incident has more events than the package holds.
4. Host, user and IP values are always masked (C2-D4); the package is built only through
   `build_package`, which returns the masking map with it. The map stays on the app host.

The function is pure: it reads no database and no clock (`created_at` is passed in).
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime

from app.contracts import (
    Event,
    EventRole,
    EvidencePackage,
    Incident,
    IncidentContext,
    LabelStatus,
)
from app.contracts.evidence import MAX_EVIDENCE_EVENTS
from app.evidence.masking import MaskedPackage, MaskingLeak, find_leaks, mask_events
from app.ingest.evidence import evidence_event

ID_LIMIT = 128


class MissingEvents(ValueError):
    """The incident links events that were not given to the builder."""


def _order(event: Event) -> tuple[datetime, str]:
    return (event.timestamp, event.event_id)


def select_events(
    incident: Incident, events: Mapping[str, Event], limit: int = MAX_EVIDENCE_EVENTS
) -> list[tuple[Event, EventRole]]:
    """The events that go into the package, in package order, with their incident role."""
    missing = sorted(link.event_id for link in incident.events if link.event_id not in events)
    if missing:
        raise MissingEvents(f"{len(missing)} linked events not given, first: {missing[0]}")
    flagged, context = [], []
    for link in incident.events:
        event = events[link.event_id]
        is_flagged = event.label.status == LabelStatus.FLAGGED
        if (link.role == EventRole.FLAGGED) != is_flagged:
            raise ValueError(
                f"event {link.event_id}: incident role {link.role.value} does not match "
                f"label {event.label.status.value}"
            )
        (flagged if is_flagged else context).append(event)
    chosen_flagged = sorted(flagged, key=_order)[:limit]
    places = limit - len(chosen_flagged)
    times = [e.timestamp for e in chosen_flagged]

    def distance(event: Event) -> float:
        return min(abs((event.timestamp - t).total_seconds()) for t in times)

    chosen_context = sorted(context, key=lambda e: (distance(e), *_order(e)))[:places]
    chosen_context.sort(key=_order)
    return [(e, EventRole.FLAGGED) for e in chosen_flagged] + [
        (e, EventRole.CONTEXT) for e in chosen_context
    ]


def _package_id(incident_id: str, content: list[dict]) -> str:
    digest = hashlib.sha256(
        json.dumps([incident_id, content], sort_keys=True, default=str).encode()
    ).hexdigest()
    package_id = f"pkg-{incident_id}-{digest[:12]}"
    if len(package_id) > ID_LIMIT:  # incident IDs can be up to 128 characters
        package_id = f"pkg-{hashlib.sha256(incident_id.encode()).hexdigest()[:24]}-{digest[:12]}"
    return package_id


def build_package(
    incident: Incident, events: Mapping[str, Event] | Iterable[Event], created_at: datetime
) -> tuple[EvidencePackage, MaskedPackage]:
    """The masked package for one incident and its masking map (C2-D1)."""
    by_id = events if isinstance(events, Mapping) else {e.event_id: e for e in events}
    chosen = select_events(incident, by_id)
    masked = mask_events(incident.incident_id, [evidence_event(e, role) for e, role in chosen])
    linked = [by_id[link.event_id] for link in incident.events]
    context = IncidentContext(
        incident_type=incident.incident_type,
        risk_score=incident.risk.score if incident.risk else None,
        risk_level=incident.risk.level if incident.risk else None,
        first_event_at=incident.first_event_at,
        last_event_at=incident.last_event_at,
        flagged_event_count=sum(1 for e in linked if e.label.status == LabelStatus.FLAGGED),
        context_event_count=sum(1 for e in linked if e.label.status != LabelStatus.FLAGGED),
        host_count=len({e.host for e in linked if e.host is not None}),
    )
    content = [event.model_dump(mode="json") for event in masked.events]
    package = EvidencePackage(
        package_id=_package_id(incident.incident_id, [context.model_dump(mode="json"), content]),
        incident_id=incident.incident_id,
        created_at=created_at,
        incident=context,
        events=list(masked.events),
        total_event_count=len(linked),
        truncated=len(masked.events) < len(linked),
        masked=True,
    )
    leaks = find_leaks(package.model_dump(mode="json"), masked.masking_map)
    if leaks:
        raise MaskingLeak(f"real {', '.join(leaks)} values are still in the package")
    return package, masked
