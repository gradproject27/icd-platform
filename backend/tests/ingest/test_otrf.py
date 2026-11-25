import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts import Event, LabelStatus
from app.ingest.cli import intake_counts
from app.ingest.event_types import EventTypes, type_names
from app.ingest.interface import IntakeContext, ParseError, Quarantined
from app.ingest.otrf import MAX_TEXT, file_offset, measure_offsets, parse_otrf, profile, type_key
from app.ingest.registry import PARSERS

SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "ingest" / "otrf-sample.json"
INGESTED_AT = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
SYSMON = "Microsoft-Windows-Sysmon/Operational"

# Expected results for fixtures/ingest/otrf-sample.json, line by line (its README).
QUARANTINED = {
    10: "empty_record",
    11: "bad_json",
    12: "not_an_object",
    13: "missing_timestamp",
    14: "bad_timestamp",
    15: "bad_timestamp",
}


def ctx(dataset_id: str = "otrf", source_file: str = "otrf-sample.json") -> IntakeContext:
    return IntakeContext(
        upload_id="upl-test", dataset_id=dataset_id, source_file=source_file,
        ingested_at=INGESTED_AT,
    )  # fmt: skip


@pytest.fixture
def items():
    return list(parse_otrf(SAMPLE, ctx()))


def by_line(items):
    out = {}
    for item in items:
        ref = item.provenance.record_ref if isinstance(item, Event) else item.record_ref
        out[int(ref.rsplit(":", 1)[1])] = item
    return out


def write(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "events.json"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def test_registered_for_otrf():
    assert {s.value: p for s, p in PARSERS.items()}["otrf"] is parse_otrf


def test_one_item_per_line_in_file_order(items):
    assert len(items) == 16
    assert sorted(by_line(items)) == list(range(1, 17))


def test_intake_counts_add_up(items):
    assert intake_counts(items).model_dump() == {
        "records_read": 16,
        "events_stored": 10,
        "flagged": 0,
        "unflagged": 0,
        "unlabelled": 10,
        "quarantined": 6,
        "quarantined_by_reason": dict(sorted(Counter(QUARANTINED.values()).items())),
    }


def test_quarantine_reasons_per_line(items):
    lines = by_line(items)
    for number, code in QUARANTINED.items():
        assert isinstance(lines[number], Quarantined), number
        assert lines[number].reason_code == code, number


def test_every_event_is_unlabelled_with_no_technique(items):
    # OTRF techniques are dataset metadata (label_scope per_dataset), never per event.
    for event in by_line(items).values():
        if isinstance(event, Event):
            assert event.label.status == LabelStatus.UNLABELLED
            assert event.label.attack_type is None and event.label.raw_value is None


def test_times_utc_and_local_with_measured_offset(items):
    lines = by_line(items)
    assert lines[1].timestamp == datetime(2020, 5, 2, 2, 55, 23, 551000, tzinfo=UTC)
    assert lines[1].extra_fields["timestamp_source"] == "UtcTime"
    assert "utc_offset_minutes" not in lines[1].extra_fields
    # Security event: EventTime 22:55:25 local, offset -240 measured from the Sysmon events.
    assert lines[3].timestamp == datetime(2020, 5, 2, 2, 55, 25, tzinfo=UTC)
    assert lines[3].extra_fields["timestamp_source"] == "EventTime"
    assert lines[3].extra_fields["utc_offset_minutes"] == -240


def test_event_ids_and_provenance(items):
    first = by_line(items)[1]
    assert first.event_id == "otrf:otrf-sample:1"
    assert first.provenance.source_format == "json"
    assert first.provenance.record_ref == "otrf-sample.json:1"


def test_event_types(items):
    lines = by_line(items)
    assert {n: lines[n].event_type for n in (1, 2, 3, 4, 5, 6, 7, 9, 16)} == {
        1: "process_creation",
        2: "network_connection",
        3: "network_connection",  # channel written "security" in lower case
        4: "logon_success",
        5: "special_privileges_logon",
        6: "powershell_script_block",
        7: "unknown",
        9: "file_create",
        16: "process_termination",
    }


def test_network_fields_from_sysmon_and_security(items):
    lines = by_line(items)
    sysmon, security = lines[2], lines[3]
    assert (str(sysmon.src_ip), sysmon.src_port, str(sysmon.dst_ip), sysmon.dst_port) == (
        "192.0.2.10", 50000, "198.51.100.20", 443,
    )  # fmt: skip
    assert sysmon.protocol == "tcp" and security.protocol == "tcp"  # "6" is tcp
    assert str(security.dst_ip) == "203.0.113.5" and security.dst_port == 80
    for name in ("SourceIp", "DestinationIp", "SourceAddress", "DestAddress", "Hostname"):
        assert name not in sysmon.extra_fields and name not in security.extra_fields


def test_bad_entity_values_become_null_and_keep_the_original(items):
    event = by_line(items)[8]
    assert event.src_ip is None and event.extra_fields["SourceAddress_raw"] == "LOCAL"
    assert event.src_port is None and event.extra_fields["SourcePort_raw"] == "70000"
    assert str(event.dst_ip) == "2001:db8::1" and event.protocol == "udp"


def test_user_and_privileged_user(items):
    lines = by_line(items)
    assert lines[1].user == "EXAMPLE\\alice"
    assert lines[4].user == "bob"  # 4624: TargetUserName, not the machine account
    assert lines[5].user == "admin" and lines[5].privileged_user is True
    assert all(
        e.privileged_user is None for n, e in lines.items() if isinstance(e, Event) and n != 5
    )
    assert lines[16].host is None  # Hostname "-" is a sentinel


def test_extra_fields_are_json_scalars_and_long_text_is_cut(items):
    lines = by_line(items)
    assert len(lines[6].extra_fields["ScriptBlockText"]) == MAX_TEXT
    assert lines[9].extra_fields["tags"] == '["beats_input", "otrf"]'
    for event in lines.values():
        if isinstance(event, Event):
            assert all(
                v is None or isinstance(v, str | int | float | bool)
                for v in event.extra_fields.values()
            )


def test_summary_never_holds_an_entity(items):
    for event in by_line(items).values():
        if isinstance(event, Event):
            for value in ("192.0.2", "198.51.100", "203.0.113", "wks1", "alice", "bob", "admin"):
                assert value not in event.summary, event.summary
    assert by_line(items)[1].summary == (
        "process creation (Microsoft-Windows-Sysmon/Operational 1), program tool.exe"
    )


def test_deterministic():
    assert list(parse_otrf(SAMPLE, ctx())) == list(parse_otrf(SAMPLE, ctx()))


def test_no_paired_event_means_unknown_time_zone(tmp_path):
    path = write(
        tmp_path,
        [
            {"Channel": "Security", "EventID": 4688, "EventTime": "2020-05-01 22:55:25"},
            {"Channel": SYSMON, "EventID": 1, "UtcTime": "2020-05-02 02:55:23.551"},
        ],
    )
    first, second = parse_otrf(path, ctx())
    assert isinstance(first, Quarantined) and first.reason_code == "unknown_time_zone"
    assert isinstance(second, Event)


def test_disagreeing_offsets_mean_unknown_time_zone(tmp_path):
    # A 12-hour clock across noon gives two offsets: the zone is ambiguous, so never guessed.
    records = [
        {"Channel": SYSMON, "EventID": 1, "UtcTime": "2020-10-18 23:50:00.000",
         "TimeCreated": "2020-10-18 07:50:00.000"},
        {"Channel": SYSMON, "EventID": 1, "UtcTime": "2020-10-18 14:00:00.000",
         "TimeCreated": "2020-10-18 10:00:00.000"},
        {"Channel": "Security", "EventID": 4689, "TimeCreated": "2020-10-18 07:51:00.000"},
    ]  # fmt: skip
    path = write(tmp_path, records)
    assert measure_offsets(path) == Counter({-960: 1, -240: 1})
    assert file_offset(measure_offsets(path)) is None
    *_, last = parse_otrf(path, ctx())
    assert isinstance(last, Quarantined) and last.reason_code == "unknown_time_zone"


def test_time_created_with_one_offset_is_converted(tmp_path):
    # As in the LSASS atomic set: TimeCreated is 16 h behind UtcTime in every pair.
    records = [
        {"Channel": SYSMON, "EventID": 10, "UtcTime": "2020-10-18 23:50:08.338",
         "TimeCreated": "2020-10-18 07:50:08.339"},
        {"Channel": "Security", "EventID": 4689, "TimeCreated": "2020-10-18 07:50:06.220"},
    ]  # fmt: skip
    _, security = parse_otrf(write(tmp_path, records), ctx())
    assert security.timestamp == datetime(2020, 10, 18, 23, 50, 6, 220000, tzinfo=UTC)
    assert security.extra_fields["utc_offset_minutes"] == -960


@pytest.mark.parametrize(
    ("record", "key"),
    [
        ({"Channel": "Security", "EventID": 4624}, "security:4624"),
        ({"Channel": " Security ", "EventID": "4624"}, "security:4624"),
        ({"Channel": "Security"}, None),
        ({"EventID": 1}, None),
        ({"Channel": "Security", "EventID": True}, None),
    ],
)
def test_type_key(record, key):
    assert type_key(record) == key


def test_event_type_map_is_in_the_vocabulary():
    types = EventTypes("otrf")
    assert types.field == "Channel:EventID"
    assert set(types.map.values()) <= type_names()
    assert all(key == key.lower() and ":" in key for key in types.map)


def test_other_dataset_and_missing_file_are_parse_errors(tmp_path):
    with pytest.raises(ParseError, match="does not read dataset unsw-nb15"):
        list(parse_otrf(SAMPLE, ctx("unsw-nb15")))
    with pytest.raises(ParseError, match="missing"):
        list(parse_otrf(tmp_path / "nope.json", ctx()))


def test_profile_holds_counts_only():
    summary = profile(SAMPLE)
    assert summary["lines"] == 16 and summary["not_a_json_object"] == 3
    assert summary["utc_offset_minutes_used"] == -240
    assert summary["event_types"]["security:5156"] == {
        "count": 2,
        "event_type": "network_connection",
    }
    text = repr(summary)
    for value in ("192.0.2", "198.51.100", "wks1", "alice", "bob", "tool.exe"):
        assert value not in text
