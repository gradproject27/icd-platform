"""Ground-truth incidents for UNSW-NB15 (decision C2-D14; docs/evaluation.md §2).

A ground-truth incident is a maximal run of attack records with the same attack category, the
same attacker IP and the same victim IP, where consecutive records are at most `gap` apart.

The inputs are what the dataset documents for each attack: its category and its attacker and
victim, and the time. They are read from the flagged events' label and addresses, which agree
100% with the official ground-truth file NUSW-NB15_GT.csv (docs/dataset-profile.md §7.3). No
correlation key, window or output is used (§14.1, CON-20).
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import timedelta

from app.contracts import Event, LabelStatus

DEFAULT_GAP = timedelta(minutes=60)


def truth_key(event: Event) -> tuple[str, str, str]:
    """(attack category, attacker, victim); a missing value is kept as an empty string."""
    return (
        event.label.attack_type or "",
        str(event.src_ip) if event.src_ip is not None else "",
        str(event.dst_ip) if event.dst_ip is not None else "",
    )


def ground_truth_incidents(events: Iterable[Event], gap: timedelta = DEFAULT_GAP) -> dict[str, str]:
    """Map each flagged event ID to a ground-truth incident ID (`gt-<n>`, numbered by start)."""
    if gap < timedelta(0):
        raise ValueError("gap must not be negative")
    runs: dict[tuple[str, str, str], list[Event]] = defaultdict(list)
    for event in events:
        if event.label.status == LabelStatus.FLAGGED:
            runs[truth_key(event)].append(event)

    groups: list[list[Event]] = []
    for members in runs.values():
        members.sort(key=lambda e: (e.timestamp, e.event_id))
        current = [members[0]]
        for previous, event in zip(members, members[1:], strict=False):
            if event.timestamp - previous.timestamp > gap:
                groups.append(current)
                current = []
            current.append(event)
        groups.append(current)

    groups.sort(key=lambda g: (g[0].timestamp, g[0].event_id))
    return {e.event_id: f"gt-{n}" for n, group in enumerate(groups, start=1) for e in group}
