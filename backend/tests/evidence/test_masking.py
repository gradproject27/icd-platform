"""Masking (T3-07): tokens, consistency, whole-value matching, leak check, un-masking."""

from datetime import UTC, datetime

from app.contracts import EventRole, EvidenceEvent, LabelStatus
from app.evidence.masking import TokenKind, find_leaks, mask_events

T = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def ee(n, summary="tcp flow", **fields):
    return EvidenceEvent(
        event_id=f"e-{n}",
        timestamp=T,
        event_type="network_flow",
        role=EventRole.FLAGGED,
        label_status=LabelStatus.FLAGGED,
        summary=summary,
        source=f"test.csv:{n}",
        **fields,
    )


def test_tokens_are_numbered_in_first_seen_order_per_kind():
    masked = mask_events(
        "inc-1",
        [
            ee(1, host="web-01", src_ip="198.51.100.7", dst_ip="203.0.113.9", user="alice"),
            ee(2, host="db-01", src_ip="203.0.113.9", dst_ip="198.51.100.7"),
        ],
    )
    first, second = masked.events
    assert (first.host, first.src_ip, first.dst_ip, first.user) == (
        "host-01",
        "ip-01",
        "ip-02",
        "user-01",
    )
    assert (second.host, second.src_ip, second.dst_ip) == ("host-02", "ip-02", "ip-01")
    assert masked.masking_map.tokens["ip-01"] == (TokenKind.IP, "198.51.100.7")


def test_nulls_stay_null_and_other_fields_are_unchanged():
    event = ee(1, src_ip="198.51.100.7")
    (masked,) = mask_events("inc-1", [event]).events
    assert masked.host is None and masked.user is None and masked.dst_ip is None
    assert masked.model_dump(exclude={"src_ip"}) == event.model_dump(exclude={"src_ip"})


def test_entity_in_a_summary_is_replaced_whole_values_only():
    masked = mask_events(
        "inc-1",
        [
            ee(1, src_ip="10.0.0.1", summary="from 10.0.0.1 to 10.0.0.12."),
            ee(2, host="web-01", summary="web-01 and web-010"),
        ],
    )
    assert masked.events[0].summary == "from ip-01 to 10.0.0.12."
    assert masked.events[1].summary == "host-01 and web-010"


def test_find_leaks_reports_the_kind_never_the_value():
    masked = mask_events("inc-1", [ee(1, host="web-01", src_ip="198.51.100.7")])
    clean = [e.model_dump(mode="json") for e in masked.events]
    assert find_leaks(clean, masked.masking_map) == []
    assert find_leaks({"x": "seen 198.51.100.7"}, masked.masking_map) == ["ip"]
    assert find_leaks("host web-01 down", masked.masking_map) == ["host"]


def test_unmask_puts_real_values_back_and_leaves_unknown_tokens():
    masked = mask_events("inc-1", [ee(1, host="web-01", src_ip="198.51.100.7")])
    text = "host-01 talked to ip-01; ip-07 is not in this incident."
    assert masked.masking_map.unmask(text) == (
        "web-01 talked to 198.51.100.7; ip-07 is not in this incident."
    )


def test_maps_are_per_incident():
    a = mask_events("inc-a", [ee(1, src_ip="198.51.100.7")])
    b = mask_events("inc-b", [ee(1, src_ip="203.0.113.9"), ee(2, src_ip="198.51.100.7")])
    assert a.events[0].src_ip == "ip-01"
    assert b.events[1].src_ip == "ip-02"


def test_hundredth_value_keeps_the_pattern():
    events = [ee(n, src_ip=f"10.0.{n // 250}.{n % 250 + 1}") for n in range(100)]
    masked = mask_events("inc-1", events)
    assert masked.events[-1].src_ip == "ip-100"
    assert masked.masking_map.unmask("ip-100") == "10.0.0.100"
