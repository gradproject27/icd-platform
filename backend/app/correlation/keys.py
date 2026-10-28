"""Relatedness keys (OD-02): normalized key values of an event. A null field gives no key."""

from app.contracts import Event, LinkKey
from app.correlation.config import CorrelationConfig

KEY_ORDER = (LinkKey.HOST, LinkKey.IP_PAIR, LinkKey.USER)

KeyValue = tuple[LinkKey, str]


def key_values(event: Event, config: CorrelationConfig) -> list[KeyValue]:
    """The event's key values in KEY_ORDER, without denylisted values."""
    values: list[KeyValue] = []
    if LinkKey.HOST in config.keys and event.host is not None:
        host = event.host.strip().lower()
        if host and host not in config.denied_hosts:
            values.append((LinkKey.HOST, host))
    if LinkKey.IP_PAIR in config.keys and event.src_ip is not None and event.dst_ip is not None:
        a, b = sorted((str(event.src_ip), str(event.dst_ip)))
        if a not in config.denied_ips and b not in config.denied_ips:
            # Unordered pair (Q2): A->B and B->A give the same value.
            values.append((LinkKey.IP_PAIR, f"{a}|{b}"))
    if LinkKey.USER in config.keys and event.user is not None:
        user = event.user.strip().casefold()
        if user and user not in config.denied_users:
            values.append((LinkKey.USER, user))
    return values


def ordered(keys: set[LinkKey]) -> list[LinkKey]:
    return [k for k in KEY_ORDER if k in keys]
