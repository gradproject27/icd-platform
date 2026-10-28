"""Event to EvidenceEvent, the citable view AI1 receives (plan section 5; OD-03).

No masking yet: entity fields are copied as they are and the package stays masked=false,
so C1's handoff refuses it until the Week 3 masker replaces host, IPs and user with tokens.
The summary never holds an entity (docs/ingestion.md section 6), so only those four fields
need masking.
"""

from app.contracts import Event, EventRole, EvidenceEvent


def evidence_event(event: Event, role: EventRole) -> EvidenceEvent:
    return EvidenceEvent(
        event_id=event.event_id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        role=role,
        label_status=event.label.status,
        attack_type=event.label.attack_type,
        host=event.host,
        src_ip=str(event.src_ip) if event.src_ip is not None else None,
        dst_ip=str(event.dst_ip) if event.dst_ip is not None else None,
        user=event.user,
        summary=event.summary,
        source=event.provenance.record_ref,
    )
