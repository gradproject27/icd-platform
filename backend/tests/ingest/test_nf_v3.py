from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts import Event, LabelStatus
from app.ingest import normalize as norm
from app.ingest.cli import intake_counts
from app.ingest.event_types import type_names
from app.ingest.interface import IntakeContext, ParseError, Quarantined
from app.ingest.labels import LabelMap
from app.ingest.nf_v3 import COLUMNS, EXTRA, l7_master, parse_nf_v3, profile
from app.ingest.registry import PARSERS

SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "ingest" / "nf-v3-sample.csv"
INGESTED_AT = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
UNSW_V3 = "nf-unsw-nb15-v3"
CIC_V3 = "nf-cse-cic-ids2018-v3"
HEADER = ",".join(COLUMNS)

# Expected results for fixtures/ingest/nf-v3-sample.csv, line by line (its README).
QUARANTINED = {
    15: "unknown_label",
    16: "unknown_attack_type",
    17: "unknown_attack_type",
    18: "label_attack_mismatch",
    19: "missing_timestamp",
    20: "bad_timestamp",
    21: "bad_timestamp",
    22: "empty_record",
    23: "wrong_column_count",
}


def ctx(dataset_id: str = UNSW_V3, source_file: str = "NF-UNSW-NB15-v3.csv") -> IntakeContext:
    return IntakeContext(
        upload_id="upl-test",
        dataset_id=dataset_id,
        source_file=source_file,
        ingested_at=INGESTED_AT,
    )


@pytest.fixture
def items():
    return list(parse_nf_v3(SAMPLE, ctx()))


def events(items):
    return [item for item in items if isinstance(item, Event)]


def by_line(items):
    out = {}
    for item in items:
        ref = item.provenance.record_ref if isinstance(item, Event) else item.record_ref
        out[int(ref.rsplit(":", 1)[1])] = item
    return out


def line(**values: str) -> str:
    """One data line: the first sample line with some columns changed."""
    base = SAMPLE.read_text(encoding="utf-8").splitlines()[1].split(",")
    row = dict(zip(COLUMNS, base, strict=True))
    row.update(values)
    return ",".join(row[name] for name in COLUMNS)


def test_registered_for_both_datasets():
    registered = {source.value: parser for source, parser in PARSERS.items()}
    assert registered[UNSW_V3] is parse_nf_v3
    assert registered[CIC_V3] is parse_nf_v3


def test_55_columns_as_checked_on_25_nov():
    assert len(COLUMNS) == 55 and len(set(COLUMNS)) == 55
    assert COLUMNS[0] == "FLOW_START_MILLISECONDS" and COLUMNS[-2:] == ("Label", "Attack")
    assert "Label" not in EXTRA and "Attack" not in EXTRA and len(EXTRA) == 47


def test_one_item_per_data_line_in_file_order(items):
    assert len(items) == 24
    assert sorted(by_line(items)) == list(range(2, 26))


def test_intake_counts_add_up(items):
    counts = intake_counts(items)
    assert counts.model_dump() == {
        "records_read": 24,
        "events_stored": 15,
        "flagged": 5,
        "unflagged": 9,
        "unlabelled": 1,
        "quarantined": 9,
        "quarantined_by_reason": dict(sorted(Counter(QUARANTINED.values()).items())),
    }


def test_quarantine_reasons_per_line(items):
    lines = by_line(items)
    for number, code in QUARANTINED.items():
        assert isinstance(lines[number], Quarantined), number
        assert lines[number].reason_code == code, number
        assert lines[number].record_ref == f"NF-UNSW-NB15-v3.csv:{number}"


def test_first_event_fields(items):
    first = by_line(items)[2]
    assert first.event_id == "nf-unsw-nb15-v3:NF-UNSW-NB15-v3:2"
    assert first.timestamp == datetime(2015, 1, 22, 11, 50, 16, tzinfo=UTC)
    assert first.ingested_at == INGESTED_AT
    assert (str(first.src_ip), first.src_port, str(first.dst_ip), first.dst_port) == (
        "192.0.2.10",
        51000,
        "198.51.100.20",
        80,
    )
    assert first.protocol == "tcp" and first.event_type == "http_request"
    assert first.host is None and first.user is None
    assert first.provenance.dataset_id == UNSW_V3
    assert first.provenance.source_format == "csv"
    assert first.extra_fields["L7_PROTO"] == "7.178"
    assert first.extra_fields["FLOW_END_MILLISECONDS"] == 1421927416120
    assert first.extra_fields["SRC_TO_DST_IAT_AVG"] == 12.5


def test_labels_and_attack_types(items):
    lines = by_line(items)
    flagged = {n: e.label.attack_type for n, e in lines.items() if isinstance(e, Event)
               and e.label.status == LabelStatus.FLAGGED}  # fmt: skip
    assert flagged == {
        6: "Exploits",
        7: "Reconnaissance",
        8: "DoS",
        9: "Backdoor",
        10: "Fuzzers",  # " Fuzzers " trimmed
    }
    assert all(e.label.raw_value == "1" for n, e in lines.items() if n in flagged)
    benign = [e for e in events(items) if e.label.status == LabelStatus.UNFLAGGED]
    assert len(benign) == 9 and all(e.label.attack_type is None for e in benign)
    assert lines[14].label.status == LabelStatus.UNLABELLED


def test_unknown_attack_spelling_is_never_guessed(items):
    lines = by_line(items)
    assert "'Backdoors'" in lines[16].reason  # listed for UNSW-NB15, not for NF-UNSW-NB15-v3
    assert "'Benign'" in lines[17].reason
    assert "'DoS'" in lines[18].reason


def test_label_never_leaks_into_extra_fields_or_event_type(items):
    for event in events(items):
        assert not {"Label", "Attack"} & set(event.extra_fields)
        assert event.event_type in type_names()


def test_event_type_from_l7_master_id(items):
    lines = by_line(items)
    assert [lines[n].event_type for n in (2, 3, 4, 5, 9, 11, 24, 25)] == [
        "http_request",
        "dns_query",
        "tls_session",
        "network_flow",
        "ssh_session",
        "unknown",
        "unknown",
        "network_flow",
    ]
    assert lines[24].extra_fields["L7_PROTO"] == "'; DROP TABLE events; --"


@pytest.mark.parametrize(
    ("raw", "master"),
    [("7.178", "7"), ("91", "91"), (" 5.0 ", "5"), ("", None), ("-", None), ("x.1", None)],
)
def test_l7_master(raw, master):
    assert l7_master(raw) == master


def test_protocol_numbers(items):
    lines = by_line(items)
    assert [lines[n].protocol for n in (2, 3, 5, 25)] == ["tcp", "udp", "icmp", "gre"]


def test_bad_entity_values_become_null_and_keep_the_original(items):
    lines = by_line(items)
    assert lines[12].src_ip is None and lines[12].extra_fields["IPV4_SRC_ADDR_raw"] == "host-a"
    assert lines[13].src_port is None and lines[13].extra_fields["L4_SRC_PORT_raw"] == "70000"


def test_summary_never_holds_an_entity(items):
    for event in events(items):
        for value in ("192.0.2", "198.51.100", "203.0.113", "host-a", "51000"):
            assert value not in event.summary, event.summary
    assert by_line(items)[2].summary == (
        "tcp flow, L7 7.178, 120 ms, 1,256 B src to dst, 8,420 B dst to src"
    )


def test_deterministic():
    assert list(parse_nf_v3(SAMPLE, ctx())) == list(parse_nf_v3(SAMPLE, ctx()))


def test_cic_classes(tmp_path):
    path = tmp_path / "slice.csv"
    rows = [
        HEADER,
        line(Label="1", Attack="Web Attacks"),
        line(Label="1", Attack="BruteForce"),
        line(Label="1", Attack="DDoS"),
        line(Label="1", Attack="Fuzzers"),  # a UNSW class, not a CIC one
        line(Label="0", Attack="Benign"),
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    got = list(parse_nf_v3(path, ctx(CIC_V3, "NF-CSE-CIC-IDS2018-v3.csv")))
    assert [i.label.attack_type for i in got[:3]] == ["Web Attacks", "BruteForce", "DDoS"]
    assert got[0].event_id == "nf-cse-cic-ids2018-v3:NF-CSE-CIC-IDS2018-v3:2"
    assert isinstance(got[3], Quarantined) and got[3].reason_code == "unknown_attack_type"
    assert got[4].label.status == LabelStatus.UNFLAGGED


def test_mapping_lists_the_dataset_page_classes():
    assert LabelMap(UNSW_V3).attack_types == {
        "Fuzzers", "Analysis", "Backdoor", "DoS", "Exploits", "Generic", "Reconnaissance",
        "Shellcode", "Worms",
    }  # fmt: skip
    assert LabelMap(CIC_V3).attack_types == {
        "BruteForce", "Bot", "DoS", "DDoS", "Infiltration", "Web Attacks",
    }  # fmt: skip


@pytest.mark.parametrize(
    "first",
    [
        line(),  # a slice cut without its header
        HEADER.replace("Attack", "attack"),
        HEADER + ",extra",
        ",".join(COLUMNS[:-1]),
    ],
)
def test_wrong_or_missing_header_stops_the_file(tmp_path, first):
    path = tmp_path / "f.csv"
    path.write_text(first + "\n" + line() + "\n", encoding="utf-8")
    with pytest.raises(ParseError, match="NetFlow v3 header"):
        list(parse_nf_v3(path, ctx()))
    with pytest.raises(ParseError, match="NetFlow v3 header"):
        profile(path)


def test_header_only_and_empty_files(tmp_path):
    header_only = tmp_path / "h.csv"
    header_only.write_text(HEADER + "\r\n", encoding="utf-8")
    assert list(parse_nf_v3(header_only, ctx())) == []
    empty = tmp_path / "e.csv"
    empty.write_bytes(b"")
    assert list(parse_nf_v3(empty, ctx())) == []


def test_other_dataset_and_missing_file_are_parse_errors(tmp_path):
    with pytest.raises(ParseError, match="does not read dataset unsw-nb15"):
        list(parse_nf_v3(SAMPLE, ctx("unsw-nb15")))
    with pytest.raises(ParseError, match="missing"):
        list(parse_nf_v3(tmp_path / "nope.csv", ctx()))


def test_profile_holds_counts_only():
    summary = profile(SAMPLE)
    assert summary["data_lines"] == 24
    assert summary["value_counts"]["Label|Attack"]["1|Exploits"] == 1
    assert summary["value_counts"]["L7_master"]["7"] >= 1
    text = repr(summary)
    for value in ("192.0.2", "198.51.100", "203.0.113", "host-a"):
        assert value not in text


def test_epoch_millis():
    assert norm.epoch_millis("1421927416000") == datetime(2015, 1, 22, 11, 50, 16, tzinfo=UTC)
    assert norm.epoch_millis("1421927416500.0").microsecond == 500000
    for bad in ("", "-", "abc", "99", "9" * 30):
        with pytest.raises(norm.BadValue):
            norm.epoch_millis(bad)
