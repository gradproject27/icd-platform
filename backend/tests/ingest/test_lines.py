"""Untrusted input: one bad line never stops the file (plan section 5 watch-outs)."""

import pytest

from app.ingest.cli import intake_counts
from app.ingest.interface import Quarantined
from app.ingest.lines import line_number, read_lines, read_original
from app.ingest.unsw_nb15 import parse_unsw_nb15


def write(tmp_path, data: bytes):
    path = tmp_path / "UNSW-NB15_1.csv"
    path.write_bytes(data)
    return path


def good_lines(sample, count=2) -> bytes:
    return b"".join(sample.read_bytes().splitlines(keepends=True)[:count])


def test_crlf_and_no_final_newline(tmp_path):
    lines = list(read_lines(write(tmp_path, b"a\r\nb\r\nc")))
    assert [(line.number, line.text) for line in lines] == [(1, "a"), (2, "b"), (3, "c")]


def test_byte_order_mark_is_dropped(tmp_path):
    assert next(read_lines(write(tmp_path, b"\xef\xbb\xbfsrcip,x\n"))).text == "srcip,x"


def test_bad_lines_are_quarantined_and_the_file_goes_on(tmp_path, sample, context):
    data = (
        good_lines(sample, 1)
        + b"\xff\xfe not utf-8\n"
        + b"x" * 70_000
        + b"\n"
        + b"192.0.2.1,\x00,oops\n"
        + b'"unterminated,quote\n'
        + good_lines(sample, 2)[len(good_lines(sample, 1)) :]
    )
    items = list(parse_unsw_nb15(write(tmp_path, data), context()))
    assert len(items) == 6
    reasons = [item.reason_code for item in items if isinstance(item, Quarantined)]
    assert reasons == ["bad_encoding", "line_too_long", "bad_encoding", "wrong_column_count"]
    counts = intake_counts(items)
    assert (counts.records_read, counts.events_stored, counts.quarantined) == (6, 2, 4)
    for item in items:
        if isinstance(item, Quarantined) and item.raw_excerpt is not None:
            assert len(item.raw_excerpt) <= 500 and "\x00" not in item.raw_excerpt
    assert items[5].provenance.record_ref == "UNSW-NB15_1.csv:6"


def test_huge_file_of_one_line_does_not_load_into_memory(tmp_path):
    path = write(tmp_path, b"y" * 5_000_000)
    lines = list(read_lines(path))
    assert [(line.number, line.code) for line in lines] == [(1, "line_too_long")]


def test_line_number_and_read_original(tmp_path, sample):
    assert line_number("UNSW-NB15_1.csv:42") == 42
    assert line_number("odd:name.csv:7") == 7
    for bad in ("file.csv", "file.csv:0", "file.csv:x"):
        with pytest.raises(ValueError):
            line_number(bad)
    assert read_original(sample, "s.csv:2").startswith("192.0.2.10,33661,")
    with pytest.raises(LookupError):
        read_original(sample, "s.csv:999")
