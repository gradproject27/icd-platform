"""What the model sees of one group: masked, label-blind, behaviour only.

Label-blind (proposed decision AI1-OP-D1): the view never holds the dataset label, label status,
attack type, incident role, risk or event IDs. If it did, the model would read "attack: DoS" and
agree, and `p_llm` would copy the label instead of adding a second opinion to the classifier's.
The event type comes from an activity field, never the label (app/ingest/event_types.py), and the
real datasets' summaries hold only protocol, service, state, duration and bytes.

Masking reuses C2's code (app/evidence/masking.py): host, user and IP values become tokens, and
the finished view is checked for real values with `find_leaks` before it can be sent.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.analysis.prompt import MARKUP_REMOVED, neutralize
from app.contracts import Event, EventRole, LabelStatus
from app.evidence.masking import MaskingLeak, MaskingMap, find_leaks, mask_events
from app.ingest.evidence import evidence_event
from app.opinion.groups import OpinionGroup

MAX_VIEW_EVENTS = 20
TOP_COUNTS = 5
# Keys that must never appear in a view (checked in tests and in build_view).
FORBIDDEN_KEYS = {"label", "label_status", "attack_type", "role", "risk", "event_id", "technique"}
LABEL_REMOVED = "[label removed]"
GROUP_TAG = re.compile(r"</?\s*event[\s_-]*group\b[^>]{0,200}>", re.IGNORECASE)


@dataclass(frozen=True)
class GroupView:
    document: dict[str, Any]
    shown_event_ids: tuple[str, ...]
    masking_map: MaskingMap


def pick_events(events: tuple[Event, ...], cap: int = MAX_VIEW_EVENTS) -> list[Event]:
    """Up to cap events spread evenly over the group, first and last always in. Deterministic."""
    if len(events) <= cap:
        return list(events)
    if cap == 1:
        return [events[0]]
    step = (len(events) - 1) / (cap - 1)
    return [events[round(i * step)] for i in range(cap)]


def _counts(values: list[str]) -> dict[str, int]:
    return dict(Counter(values).most_common(TOP_COUNTS))


def _redact_label(summary: str, attack_type: str | None) -> str:
    """Safety net: a summary that names the event's own attack type would leak the label.

    The real parsers never write it (their summaries are protocol, service, state, duration and
    bytes), but a hand-written or future source could ("Generic attack seen on ...").
    """
    if not attack_type:
        return summary
    pattern = re.compile(rf"(?<!\w){re.escape(attack_type.strip())}(?!\w)", re.IGNORECASE)
    return pattern.sub(LABEL_REMOVED, summary)


def _strip_group_tags(value: Any) -> Any:
    """The report prompt's filter knows its own tag names; this one removes the opinion fence's."""
    if isinstance(value, str):
        return GROUP_TAG.sub(MARKUP_REMOVED, value)
    if isinstance(value, list):
        return [_strip_group_tags(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_group_tags(item) for key, item in value.items()}
    return value


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for item in value.values() for k in _keys(item)}
    if isinstance(value, list):
        return {k for item in value for k in _keys(item)}
    return set()


def build_view(group: OpinionGroup, cap: int = MAX_VIEW_EVENTS) -> GroupView:
    shown = pick_events(group.events, cap)
    evidence = [
        evidence_event(
            e,
            EventRole.FLAGGED if e.label.status == LabelStatus.FLAGGED else EventRole.CONTEXT,
        )
        for e in shown
    ]
    masked = mask_events(f"opinion:{group.technique}:{group.entity}", evidence)
    start = group.events[0].timestamp
    rows = []
    for original, view in zip(shown, masked.events, strict=True):
        row: dict[str, Any] = {
            "t": round((original.timestamp - start).total_seconds(), 3),
            "type": view.event_type,
            "protocol": original.protocol,
            "src": view.src_ip or view.host or view.user,
            "dst": view.dst_ip,
            "dst_port": original.dst_port,
            "summary": _redact_label(view.summary, original.label.attack_type),
        }
        if view.user is not None and row["src"] != view.user:
            row["user"] = view.user
        rows.append({k: v for k, v in row.items() if v is not None})

    all_events = group.events
    span = (all_events[-1].timestamp - all_events[0].timestamp).total_seconds()
    document: dict[str, Any] = {
        "event_count": len(all_events),
        "shown_count": len(shown),
        "span_seconds": round(span, 3),
        # Counted over every event of the group; destinations as a number, never as values.
        "distinct_dst_ips": len({e.dst_ip for e in all_events if e.dst_ip is not None}),
        "distinct_dst_ports": len({e.dst_port for e in all_events if e.dst_port is not None}),
        "event_types": _counts([e.event_type for e in all_events]),
        "protocols": _counts([e.protocol for e in all_events if e.protocol is not None]),
        "events": rows,
    }
    document, _ = neutralize(document)
    document = _strip_group_tags(document)

    leaks = find_leaks(document, masked.masking_map)
    if leaks:
        raise MaskingLeak(f"real {', '.join(leaks)} values are still in the opinion view")
    bad = _keys(document) & FORBIDDEN_KEYS
    if bad:
        raise ValueError(f"label-revealing keys in the opinion view: {sorted(bad)}")
    return GroupView(document, tuple(e.event_id for e in shown), masked.masking_map)
