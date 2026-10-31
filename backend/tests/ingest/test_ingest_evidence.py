from app.contracts import Event, EventRole
from app.ingest.evidence import evidence_event
from app.ingest.unsw_nb15 import parse_unsw_nb15


def test_evidence_event_from_parsed_events(sample, context):
    items = list(parse_unsw_nb15(sample, context()))
    flagged, context_event = items[5], items[0]
    view = evidence_event(flagged, EventRole.FLAGGED)
    assert view.event_id == flagged.event_id
    assert view.attack_type == "Exploits" and view.label_status == "flagged"
    assert view.src_ip == "203.0.113.20" and view.host is None
    assert view.source == "UNSW-NB15_1.csv:6"
    assert evidence_event(context_event, EventRole.CONTEXT).role == "context"
    assert all(isinstance(item, Event) for item in (flagged, context_event))
