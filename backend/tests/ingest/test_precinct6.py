import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts import Event, LabelStatus
from app.ingest.cli import intake_counts
from app.ingest.interface import IntakeContext, ParseError, Quarantined
from app.ingest.precinct6 import CON20, parse_precinct6, profile
from app.ingest.registry import PARSERS

SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "ingest" / "precinct6-sample.jsonl"
INGESTED_AT = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

# Expected results for fixtures/ingest/precinct6-sample.jsonl, line by line (its README).
QUARANTINED = {
    6: "unknown_label",
    7: "missing_record_id",
    8: "missing_timestamp",
    9: "bad_timestamp",
    10: "empty_record",
    11: "bad_json",
}


def ctx(dataset_id: str = "precinct6") -> IntakeContext:
    return IntakeContext(
        upload_id="upl-test", dataset_id=dataset_id, source_file="precinct6-sample.jsonl",
        ingested_at=INGESTED_AT,
    )  # fmt: skip


@pytest.fixture
def items():
    return list(parse_precinct6(SAMPLE, ctx()))


def by_line(items):
    out = {}
    for item in items:
        ref = item.provenance.record_ref if isinstance(item, Event) else item.record_ref
        out[int(ref.rsplit(":", 1)[1])] = item
    return out


def test_registered_for_precinct6():
    assert {s.value: p for s, p in PARSERS.items()}["precinct6"] is parse_precinct6


def test_intake_counts_add_up(items):
    assert len(items) == 13
    assert intake_counts(items).model_dump() == {
        "records_read": 13,
        "events_stored": 7,
        "flagged": 1,
        "unflagged": 5,
        "unlabelled": 1,
        "quarantined": 6,
        "quarantined_by_reason": dict(sorted(Counter(QUARANTINED.values()).items())),
    }


def test_quarantine_reasons_per_line(items):
    lines = by_line(items)
    for number, code in QUARANTINED.items():
        assert isinstance(lines[number], Quarantined), number
        assert lines[number].reason_code == code, number


def test_labels_follow_the_mapping(items):
    lines = by_line(items)
    assert (lines[1].label.status, lines[1].label.raw_value) == (LabelStatus.FLAGGED, "malicious")
    assert (lines[2].label.status, lines[2].label.raw_value) == (LabelStatus.UNFLAGGED, "benign")
    # suspicious is context, never discarded, raw value visible (profile Q7).
    assert (lines[3].label.status, lines[3].label.raw_value) == (
        LabelStatus.UNFLAGGED,
        "suspicious",
    )
    assert lines[12].label.status == LabelStatus.UNLABELLED
    assert all(e.label.attack_type is None for e in lines.values() if isinstance(e, Event))


def test_con20_columns_never_reach_the_event(items):
    for event in by_line(items).values():
        if isinstance(event, Event):
            assert not CON20 & set(event.extra_fields)
            dumped = event.model_dump_json()
            for value in ("INC-0007", "rule-12", "Exploit chain", "T1190", "true_positive"):
                assert value not in dumped


def test_first_event_fields(items):
    first = by_line(items)[1]
    assert first.event_id == "precinct6:art-0001"
    assert first.timestamp == datetime(2024, 7, 29, 0, 0, 1, tzinfo=UTC)
    assert (first.host, first.user) == ("HOST-0001", "USER-0001")
    assert (str(first.src_ip), first.src_port, str(first.dst_ip), first.dst_port) == (
        "192.0.2.10", 51000, "198.51.100.20", 443,
    )  # fmt: skip
    assert first.protocol == "tcp"
    assert first.event_type == "unknown"  # message_type map stays empty until profiled
    assert first.provenance.source_format == "json"
    assert first.extra_fields["severity"] == "high"
    assert first.extra_fields["message_type"] == "fw_allow"


def test_entities_empty_host_names_and_sentinels(items):
    lines = by_line(items)
    assert lines[2].src_ip is None and "src_ip_raw" not in lines[2].extra_fields
    assert lines[4].src_ip is None and lines[4].extra_fields["src_ip_raw"] == "HOST-0042"
    assert lines[5].src_ip is None and "src_ip_raw" not in lines[5].extra_fields
    assert lines[13].src_port is None and lines[13].extra_fields["src_port_raw"] == "70000"
    assert lines[13].timestamp == datetime(2024, 7, 29, 0, 0, 13, 500000, tzinfo=UTC)


def test_summary_never_holds_an_entity(items):
    for event in by_line(items).values():
        if isinstance(event, Event):
            for value in ("192.0.2", "198.51.100", "HOST-", "USER-", "ORG-"):
                assert value not in event.summary


def test_parquet_upload_is_refused_with_the_export_command(tmp_path):
    path = tmp_path / "signals.parquet"
    path.write_bytes(b"PAR1" + b"\x00" * 16)
    with pytest.raises(ParseError, match="precinct6_export"):
        list(parse_precinct6(path, ctx()))


def test_other_dataset_and_missing_file_are_parse_errors(tmp_path):
    with pytest.raises(ParseError, match="does not read dataset otrf"):
        list(parse_precinct6(SAMPLE, ctx("otrf")))
    with pytest.raises(ParseError, match="missing"):
        list(parse_precinct6(tmp_path / "nope.jsonl", ctx()))


def test_deterministic():
    assert list(parse_precinct6(SAMPLE, ctx())) == list(parse_precinct6(SAMPLE, ctx()))


def test_profile_holds_counts_only():
    summary = profile(SAMPLE)
    assert summary["lines"] == 13 and summary["not_a_json_object"] == 2
    assert summary["label_binary"]["malicious"] == 1
    assert summary["message_type"]["fw_allow"]["event_type"] == "unknown"
    text = repr(summary)
    for value in ("192.0.2", "HOST-0001", "USER-0001", "INC-0007", "connection allowed"):
        assert value not in text


def test_export_parquet_slice_round_trip(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    from app.ingest.precinct6_export import export, main

    records = [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines()[:5]]
    for record in records:
        record["timestamp"] = datetime.fromtimestamp(record["timestamp"], tz=UTC)
    source = tmp_path / "signals.parquet"
    pq.write_table(pa.Table.from_pylist(records), source)

    out = tmp_path / "slice.jsonl"
    start, end = (
        datetime(2024, 7, 29, 0, 0, 2, tzinfo=UTC),
        datetime(2024, 7, 29, 0, 0, 4, tzinfo=UTC),
    )
    assert export(source, out, start=start.timestamp(), end=end.timestamp(), limit=None) == 2
    exported = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["artifact_id"] for r in exported] == ["art-0002", "art-0003"]
    assert exported[0]["timestamp"] == 1722211202.0  # datetime column -> epoch seconds
    assert exported[1]["matched_rules"] == ["rule-3"]  # columns unchanged; the parser drops CON-20

    events = list(parse_precinct6(out, ctx()))
    assert [e.event_id for e in events] == ["precinct6:art-0002", "precinct6:art-0003"]

    assert main([str(source), "--out", str(out), "--limit", "1"]) == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1
