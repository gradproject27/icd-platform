"""Who a simulated action is about: target host, external source IP, involved account (D3).

Only the incident's flagged events count; context events are never treated as malicious (OD-02).
Ties are broken the same way every time, so the same incident always gives the same targets.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from app.contracts import Event, EventRole, Incident
from app.response.config import ResponseConfig


@dataclass(frozen=True)
class Targets:
    host: str | None
    source_ip: str | None
    account: str | None

    def as_details(self) -> dict[str, str | None]:
        return {"host": self.host, "source_ip": self.source_ip, "account": self.account}


def flagged_events(incident: Incident, events: Iterable[Event]) -> list[Event]:
    """The incident's flagged events, in the incident's order. Unknown IDs are an error."""
    by_id = {event.event_id: event for event in events}
    missing = [link.event_id for link in incident.events if link.event_id not in by_id]
    if missing:
        raise ValueError(f"events missing for incident {incident.incident_id}: {missing}")
    return [by_id[link.event_id] for link in incident.events if link.role == EventRole.FLAGGED]


def _most_common(counts: Counter[str], tie_key=lambda value: value) -> str | None:
    if not counts:
        return None
    return min(counts, key=lambda value: (-counts[value], tie_key(value)))


def find_targets(incident: Incident, events: Iterable[Event], config: ResponseConfig) -> Targets:
    """Targets of the incident (response spec sections 6 and 9, decision D3).

    host: the host on the most flagged events; else the internal destination IP on the most.
    source_ip: the external source IP on the most flagged events.
    account: the user on the most flagged events; ties prefer a privileged account.
    Each tie that is left goes to the alphabetically first value.
    """
    flagged = flagged_events(incident, events)

    hosts = Counter(e.host for e in flagged if e.host is not None)
    host = _most_common(hosts)
    if host is None:
        internal_dst = Counter(
            str(e.dst_ip) for e in flagged if e.dst_ip is not None and config.is_internal(e.dst_ip)
        )
        host = _most_common(internal_dst)

    external_src = Counter(
        str(e.src_ip) for e in flagged if e.src_ip is not None and not config.is_internal(e.src_ip)
    )

    accounts = Counter(e.user for e in flagged if e.user is not None)
    privileged = {e.user for e in flagged if e.user is not None and e.privileged_user}
    account = _most_common(accounts, tie_key=lambda user: (user not in privileged, user))

    return Targets(host=host, source_ip=_most_common(external_src), account=account)
