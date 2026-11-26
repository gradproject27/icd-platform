"""The confidence handoff to HPC (risk-v1 step 6b, user decision of 26 Nov 2026: the models run
as an HPC batch job, not in the worker).

The worker writes one input file per upload and the cluster answers with one output file:

    input  (INPUT_FORMAT)   the 47 flow features of every flagged NetFlow v3 event of the
                            upload's incidents, and the masked description of every evidence
                            group (technique, entity) for the LLM. No IP, port, time, host, user
                            or label is in it: features.py excludes them and groups.py masks.
    output (OUTPUT_FORMAT)  per event: C, p_clf, p_llm and its flags; the versions behind them;
                            or an error for the whole run.

The cluster side is app.confidence.batch_run. This module has no NumPy, so it runs in the worker.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.confidence import features as F
from app.confidence.groups import group_from_events
from app.confidence.values import Confidence, clamp
from app.contracts import Event, EventRole, Incident, LabelStatus
from app.correlation.risk import EventConfidences, entity_of
from app.ingest.normalize import IANA_PROTOCOLS

INPUT_FORMAT = "icd-confidence-input-v1"
OUTPUT_FORMAT = "icd-confidence-output-v1"
_PROTOCOL_NUMBERS = {name: number for number, name in IANA_PROTOCOLS.items()}


def _feature(event: Event, name: str) -> float | None:
    if name == "PROTOCOL":
        value: Any = _PROTOCOL_NUMBERS.get(event.protocol or "", event.protocol)
    else:
        value = event.extra_fields.get(name)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # L7_PROTO "7.178" -> 7.178, as prepare.py reads the CSV
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def build_input(
    request_id: str, incidents: Iterable[Incident], events: Mapping[str, Event]
) -> dict[str, Any]:
    """The input file for one upload's incidents (flagged NetFlow v3 events only)."""
    rows: dict[str, dict[str, Any]] = {}
    groups: list[dict[str, Any]] = []
    for incident in incidents:
        flagged = [
            events[link.event_id]
            for link in incident.events
            if link.role == EventRole.FLAGGED
            and events[link.event_id].provenance.dataset_id in F.DATASETS
            and events[link.event_id].label.status == LabelStatus.FLAGGED
        ]
        keys = sorted({(e.label.attack_type or "unknown", entity_of(e)) for e in flagged})
        for technique, entity in keys:
            group = group_from_events(flagged, technique, entity, incident.incident_id)
            if group is None:
                continue
            members = [
                e.event_id
                for e in flagged
                if (e.label.attack_type or "unknown", entity_of(e)) == (technique, entity)
            ]
            evidence = group.evidence()
            groups.append(
                {
                    "group_id": group.group_id,
                    "incident_id": incident.incident_id,
                    "event_ids": sorted(members),
                    "evidence": evidence,
                    "evidence_sha256": hashlib.sha256(
                        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                }
            )
        for event in flagged:
            rows[event.event_id] = {
                "event_id": event.event_id,
                "features": [_feature(event, name) for name in F.FEATURES],
            }
    return {
        "format": INPUT_FORMAT,
        "request_id": request_id,
        "feature_set": F.FEATURE_SET_VERSION,
        "features": list(F.FEATURES),
        "events": [rows[k] for k in sorted(rows)],
        "groups": groups,
    }


class EventValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    c: float = Field(ge=0, le=1)
    p_clf: float | None = Field(default=None, ge=0, le=1)
    p_llm: float | None = Field(default=None, ge=0, le=1)
    flags: list[str] = Field(default_factory=list)


class ConfidenceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = OUTPUT_FORMAT
    request_id: str
    version: str | None = None  # short name for config_version, e.g. "clf-…+llm-…+stack-…"
    versions: dict[str, str] = Field(default_factory=dict)
    events: dict[str, EventValue] = Field(default_factory=dict)
    error: str | None = None


ALLOWED_FLAGS = {"needs_review", "llm_pending", "llm_unavailable"}


def to_confidences(output: ConfidenceOutput) -> EventConfidences:
    """The final (phase 2) confidences of a successful output. Values are clamped again and
    unknown flags dropped, so a cluster answer can never push C outside 0.05 to 1."""
    if output.error is not None or output.version is None:
        raise ValueError(f"the confidence run failed: {output.error or 'no version'}")
    values = {
        event_id: Confidence(
            clamp(v.c), v.p_clf, v.p_llm, tuple(f for f in v.flags if f in ALLOWED_FLAGS)
        )
        for event_id, v in output.events.items()
    }
    return EventConfidences(values, output.version, phase="final", versions=output.versions)


def fixed_only() -> EventConfidences:
    """No event an available model applies to: every flagged event keeps its fixed C."""
    return EventConfidences({}, "confidence-none")


def pending(flag: str = "llm_pending") -> EventConfidences:
    """Phase 1 before the HPC answer (llm_pending), or after it failed (llm_unavailable): no
    model value yet, so every flagged event keeps its dataset's fixed C (confidence_fixed)."""
    return EventConfidences({}, "confidence-" + flag.split("_", 1)[1], incident_flag=flag)
