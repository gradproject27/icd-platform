"""Incident key facts: what an analyst reads first, computed by code from the flagged events.

Proposal P1 of the competitor feature study (PR #51, section F-I: the fields of an incident
summary such as start time, starting entity, assets and indicators). ICD computes them
deterministically instead of asking the model, so they need no grounding check and never reach
the model: the evidence package, the prompts and the AnalysisReport stay as they are.

Rules (same as the response engine's targets, response/targets.py):
- Only the incident's flagged events count. Context events are never indicators (OD-02).
- Internal and external addresses follow response.toml [network], not Python's is_private, so
  documentation ranges such as 203.0.113.0/24 count as external (decision D3).
- Events are ordered by (timestamp, event_id); lists by first appearance, then value. The same
  incident and events always give the same facts.
- Every item cites the flagged events it comes from (at most MAX_CITED, oldest first).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

from app.contracts import Event, EventRole, Incident
from app.response.config import ResponseConfig
from app.response.targets import flagged_events

# Items per list and cited events per item. A longer list is cut and `truncated` is set.
MAX_ITEMS = 20
MAX_CITED = 10


@dataclass(frozen=True)
class KeyFactItem:
    value: str
    event_count: int
    first_seen: datetime
    event_ids: list[str]


@dataclass(frozen=True)
class KeyFacts:
    incident_id: str
    network_config_version: str
    first_flagged_event_id: str
    started_at: datetime
    last_flagged_event_id: str
    last_flagged_at: datetime
    started_on: str | None
    origin_ip: str | None
    flagged_event_count: int
    context_event_count: int
    attack_types: list[KeyFactItem] = field(default_factory=list)
    hosts: list[KeyFactItem] = field(default_factory=list)
    internal_ips: list[KeyFactItem] = field(default_factory=list)
    external_ips: list[KeyFactItem] = field(default_factory=list)
    destination_ports: list[KeyFactItem] = field(default_factory=list)
    accounts: list[KeyFactItem] = field(default_factory=list)
    truncated: bool = False


def _order(event: Event) -> tuple[datetime, str]:
    return (event.timestamp, event.event_id)


def _collect(
    events: list[Event], values_of: Callable[[Event], Iterable[str]]
) -> tuple[list[KeyFactItem], bool]:
    """One item per distinct value over `events` (already in order). Returns (items, cut)."""
    seen: dict[str, list[Event]] = {}
    for event in events:
        for value in dict.fromkeys(values_of(event)):  # an event counts once per value
            seen.setdefault(value, []).append(event)
    items = [
        KeyFactItem(
            value=value,
            event_count=len(hits),
            first_seen=hits[0].timestamp,
            event_ids=[e.event_id for e in hits[:MAX_CITED]],
        )
        for value, hits in seen.items()
    ]
    items.sort(key=lambda item: (item.first_seen, item.value))
    return items[:MAX_ITEMS], len(items) > MAX_ITEMS


def key_facts(incident: Incident, events: Iterable[Event], config: ResponseConfig) -> KeyFacts:
    """Key facts of one incident. Raises ValueError if an event of the incident is missing."""
    flagged = sorted(flagged_events(incident, events), key=_order)
    if not flagged:
        # The Incident contract requires a flagged event; this keeps the error explicit.
        raise ValueError(f"{incident.incident_id}: no flagged event")
    first, last = flagged[0], flagged[-1]

    def ips(event: Event, internal: bool) -> list[str]:
        return [
            str(ip)
            for ip in (event.src_ip, event.dst_ip)
            if ip is not None and config.is_internal(ip) == internal
        ]

    started_on = first.host
    if started_on is None and first.dst_ip is not None and config.is_internal(first.dst_ip):
        started_on = str(first.dst_ip)
    origin_ip = (
        str(first.src_ip)
        if first.src_ip is not None and not config.is_internal(first.src_ip)
        else None
    )

    lists = {
        "attack_types": _collect(
            flagged, lambda e: [e.label.attack_type] if e.label.attack_type else []
        ),
        "hosts": _collect(flagged, lambda e: [e.host] if e.host else []),
        "internal_ips": _collect(flagged, lambda e: ips(e, internal=True)),
        "external_ips": _collect(flagged, lambda e: ips(e, internal=False)),
        "destination_ports": _collect(
            flagged, lambda e: [str(e.dst_port)] if e.dst_port is not None else []
        ),
        "accounts": _collect(flagged, lambda e: [e.user] if e.user else []),
    }
    return KeyFacts(
        incident_id=incident.incident_id,
        network_config_version=config.config_version,
        first_flagged_event_id=first.event_id,
        started_at=first.timestamp,
        last_flagged_event_id=last.event_id,
        last_flagged_at=last.timestamp,
        started_on=started_on,
        origin_ip=origin_ip,
        flagged_event_count=len(flagged),
        context_event_count=sum(1 for link in incident.events if link.role == EventRole.CONTEXT),
        truncated=any(cut for _, cut in lists.values()),
        **{name: items for name, (items, _) in lists.items()},
    )
