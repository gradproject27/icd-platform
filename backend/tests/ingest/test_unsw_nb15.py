from collections import Counter

import pytest

from app.contracts import Event, LabelStatus
from app.ingest.cli import intake_counts
from app.ingest.event_types import type_names
from app.ingest.interface import ParseError, Quarantined
from app.ingest.registry import PARSERS
from app.ingest.unsw_nb15 import COLUMNS, parse_unsw_nb15

# Expected results for fixtures/ingest/unsw-nb15-sample.csv, line by line (its README).
QUARANTINED = {
    23: "unknown_label",
    24: "unknown_label",
    25: "bad_timestamp",
    26: "missing_timestamp",
    27: "bad_timestamp",
    28: "empty_record",
    29: "wrong_column_count",
}


@pytest.fixture
def items(sample, context):
    return list(parse_unsw_nb15(sample, context()))


def events(items):
    return [item for item in items if isinstance(item, Event)]


def test_registered_for_unsw_nb15():
    assert any(source.value == "unsw-nb15" for source in PARSERS)


def test_49_columns():
    assert len(COLUMNS) == 49 and len(set(COLUMNS)) == 49
    assert COLUMNS[28] == "Stime" and COLUMNS[47:] == ("attack_cat", "Label")


def test_one_item_per_line_in_file_order(items):
    assert len(items) == 30
    refs = [
        item.provenance.record_ref if isinstance(item, Event) else item.record_ref for item in items
    ]
    assert refs == [f"UNSW-NB15_1.csv:{n}" for n in range(1, 31)]


def test_intake_counts_add_up(items):
    counts = intake_counts(items)
    assert counts.model_dump() == {
        "records_read": 30,
        "events_stored": 23,
        "flagged": 13,
        "unflagged": 9,
        "unlabelled": 1,
        "quarantined": 7,
        "quarantined_by_reason": {
            "bad_timestamp": 2,
            "empty_record": 1,
            "missing_timestamp": 1,
            "unknown_label": 2,
            "wrong_column_count": 1,
        },
    }


def test_quarantine_reasons_per_line(items):
    found = {
        int(item.record_ref.rsplit(":", 1)[1]): item.reason_code
        for item in items
        if isinstance(item, Quarantined)
    }
    assert found == QUARANTINED
    for item in items:
        if isinstance(item, Quarantined):
            assert item.reason
            assert item.reason_code == "empty_record" or item.raw_excerpt


def test_every_event_links_to_its_original_line(items):
    for number, item in enumerate(items, start=1):
        if isinstance(item, Event):
            assert item.event_id == f"unsw-nb15:UNSW-NB15_1:{number}"
            assert item.provenance.model_dump() == {
                "dataset_id": "unsw-nb15",
                "source_file": "UNSW-NB15_1.csv",
                "record_ref": f"UNSW-NB15_1.csv:{number}",
                "source_format": "csv",
            }


def test_first_event_fields(items):
    event = items[0]
    assert event.timestamp.isoformat() == "2015-01-22T11:50:00+00:00"
    assert event.ingested_at.isoformat() == "2026-10-28T12:00:00+00:00"
    assert event.event_type == "dns_query"
    assert (str(event.src_ip), event.src_port, str(event.dst_ip), event.dst_port) == (
        "192.0.2.10",
        1390,
        "198.51.100.5",
        53,
    )
    assert event.protocol == "udp"
    assert event.label.status == LabelStatus.UNFLAGGED and event.label.raw_value == "0"
    assert event.host is None and event.user is None and event.privileged_user is None
    assert event.summary == "udp flow, service dns, state CON, 0.04 s, 528 B out, 304 B in"


def test_labels_and_attack_types(items):
    flagged = [event for event in events(items) if event.label.status == LabelStatus.FLAGGED]
    assert len(flagged) == 13
    assert all(event.label.raw_value == "1" for event in flagged)
    assert Counter(event.label.attack_type for event in flagged) == {
        "Exploits": 2,
        "Reconnaissance": 2,
        "Fuzzers": 2,
        "Backdoor": 1,
        "Backdoors": 1,
        "Generic": 1,
        "DoS": 1,
        "Shellcode": 1,
        "Worms": 1,
        "Analysis": 1,
    }


def test_missing_label_stays_unlabelled(items):
    event = items[21]
    assert event.label.status == LabelStatus.UNLABELLED and event.label.raw_value is None


def test_label_never_leaks_into_extra_fields_or_event_type(items):
    for event in events(items):
        assert not {"Label", "attack_cat"} & set(event.extra_fields)
        assert event.event_type in type_names()


def test_hex_and_missing_ports(items):
    assert (items[3].src_port, items[3].dst_port) == (11, 49320)
    assert (items[4].src_port, items[4].dst_port) == (None, None)
    assert items[4].event_type == "network_flow"


def test_bad_entity_values_become_null_and_keep_the_original(items):
    host_name = items[18]
    assert host_name.src_ip is None and host_name.extra_fields["srcip_raw"] == "host-a"
    big_port = items[29]
    assert big_port.src_port is None and big_port.extra_fields["sport_raw"] == "70000"


def test_unknown_service_and_injection_text_are_data(items):
    assert items[19].event_type == "unknown"
    assert items[20].event_type == "unknown"
    assert items[20].extra_fields["service"] == "'; DROP TABLE events; --"


def test_summary_never_holds_an_entity(items):
    for event in events(items):
        for value in (event.src_ip, event.dst_ip, event.src_port, event.dst_port):
            if value is not None and value not in (0,):
                assert str(value) not in event.summary.split(", ")[0]
        assert "192.0.2." not in event.summary and "198.51.100." not in event.summary
        assert "203.0.113." not in event.summary


def test_deterministic(sample, context):
    first = [item for item in parse_unsw_nb15(sample, context())]
    second = [item for item in parse_unsw_nb15(sample, context())]
    assert first == second


def test_event_ids_are_stable_per_file_name(sample, context):
    renamed = list(parse_unsw_nb15(sample, context("flows copy (2).csv")))
    assert renamed[0].event_id == "unsw-nb15:flows_copy_2:1"
    assert renamed[0].provenance.source_file == "flows copy (2).csv"


def test_header_line_is_skipped_and_not_counted(tmp_path, sample, context):
    file = tmp_path / "with-header.csv"
    file.write_text(",".join(COLUMNS) + "\n" + sample.read_text(), encoding="utf-8")
    items = list(parse_unsw_nb15(file, context("with-header.csv")))
    assert len(items) == 30
    assert items[0].provenance.record_ref == "with-header.csv:2"


def test_missing_file_is_a_parse_error(tmp_path, context):
    with pytest.raises(ParseError):
        list(parse_unsw_nb15(tmp_path / "gone.csv", context()))
