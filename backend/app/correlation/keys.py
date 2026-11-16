"""Relatedness keys (OD-02): normalized key values of an event. A null field gives no key."""

from app.contracts import Event, LinkKey
from app.correlation.config import CorrelationConfig

KEY_ORDER = (LinkKey.HOST, LinkKey.IP_PAIR, LinkKey.USER)

KeyValue = tuple[LinkKey, str]


def key_values(event: Event, config: CorrelationConfig) -> list[KeyValue]:
    """The event's key values in KEY_ORDER, without denylisted values."""
    return key_values_of(
        event.host,
        None if event.src_ip is None else str(event.src_ip),
        None if event.dst_ip is None else str(event.dst_ip),
        event.user,
        config,
    )


def key_values_of(
    host: str | None,
    src_ip: str | None,
    dst_ip: str | None,
    user: str | None,
    config: CorrelationConfig,
) -> list[KeyValue]:
    """Key values from the raw fields (IPs as str() of the address, as the events table keeps
    them), so a stored event can be matched without loading it."""
    values: list[KeyValue] = []
    if LinkKey.HOST in config.keys and host is not None:
        host = host.strip().lower()
        if host and host not in config.denied_hosts:
            values.append((LinkKey.HOST, host))
    if LinkKey.IP_PAIR in config.keys and src_ip is not None and dst_ip is not None:
        a, b = sorted((src_ip, dst_ip))
        if a not in config.denied_ips and b not in config.denied_ips:
            # Unordered pair (Q2): A->B and B->A give the same value.
            values.append((LinkKey.IP_PAIR, f"{a}|{b}"))
    if LinkKey.USER in config.keys and user is not None:
        user = user.strip().casefold()
        if user and user not in config.denied_users:
            values.append((LinkKey.USER, user))
    return values


def ordered(keys: set[LinkKey]) -> list[LinkKey]:
    return [k for k in KEY_ORDER if k in keys]
