"""Export stored events as Elastic Common Schema (ECS) documents (P7, competitor study F-J).

An export view only: ICD's Event contract keeps its own field names, and nothing here changes an
event. Pinned to the released ECS 9.5.0 (elastic/ecs tag v9.5.0, commit 401807e, Apache-2.0):
every ECS field written is in ECS_FIELDS, each checked in that release's generated/csv/fields.csv
(THIRD_PARTY_NOTICES.md). ICD's own fields (the dataset label, event type, provenance) have no ECS
equivalent and go under the custom `icd.` object. Empty values are left out.
"""

from typing import Any

from app.contracts import Event, LabelStatus
from app.correlation.tactics import TacticsConfig, load_tactics_config

ECS_VERSION = "9.5.0"

# The ECS 9.5.0 fields this export writes (all checked in the release's fields.csv).
ECS_FIELDS = frozenset(
    {
        "@timestamp",
        "ecs.version",
        "event.id",
        "event.ingested",
        "event.kind",
        "event.dataset",
        "host.name",
        "source.ip",
        "source.port",
        "destination.ip",
        "destination.port",
        "network.transport",
        "network.protocol",
        "user.name",
        "message",
        "threat.framework",
        "threat.tactic.id",
        "threat.tactic.name",
    }
)

# IANA transport protocols go to network.transport; anything else is an application protocol.
TRANSPORTS = frozenset({"tcp", "udp", "icmp", "sctp", "ipv6-icmp"})


def _iso(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _prune(doc: dict[str, Any]) -> dict[str, Any]:
    """Drop None values and the objects left empty."""
    out = {}
    for key, value in doc.items():
        if isinstance(value, dict):
            value = _prune(value)
            if value:
                out[key] = value
        elif value is not None:
            out[key] = value
    return out


def to_ecs(event: Event, tactics: TacticsConfig | None = None) -> dict[str, Any]:
    """One ECS 9.5.0 document for one stored event."""
    tactics = tactics or load_tactics_config()
    flagged = event.label.status == LabelStatus.FLAGGED
    protocol = event.protocol.strip().lower() if event.protocol else None
    found = tactics.tactics_for(event.label.attack_type) if flagged else ()
    doc = {
        "@timestamp": _iso(event.timestamp),
        "ecs": {"version": ECS_VERSION},
        "event": {
            "id": event.event_id,
            "ingested": _iso(event.ingested_at),
            # A dataset-flagged event is an alert in ECS terms; ICD never flags anything itself.
            "kind": "alert" if flagged else "event",
            "dataset": event.provenance.dataset_id,
        },
        "host": {"name": event.host},
        "source": {
            "ip": str(event.src_ip) if event.src_ip else None,
            "port": event.src_port,
        },
        "destination": {
            "ip": str(event.dst_ip) if event.dst_ip else None,
            "port": event.dst_port,
        },
        "network": {
            "transport": protocol if protocol in TRANSPORTS else None,
            "protocol": protocol if protocol and protocol not in TRANSPORTS else None,
        },
        "user": {"name": event.user},
        "message": event.summary,
        "threat": {
            "framework": "MITRE ATT&CK",
            "tactic": {"id": [i for i, _ in found], "name": [n for _, n in found]},
        }
        if found
        else None,
        "icd": {
            "event_type": event.event_type,
            "label": {
                "status": event.label.status.value,
                "raw_value": event.label.raw_value,
                "attack_type": event.label.attack_type,
            },
            "privileged_user": event.privileged_user,
            "provenance": {
                "source_file": event.provenance.source_file,
                "record_ref": event.provenance.record_ref,
                "source_format": event.provenance.source_format,
            },
            "tactics_config_version": tactics.config_version if found else None,
        },
    }
    return _prune(doc)
