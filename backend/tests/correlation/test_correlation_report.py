"""The correlation and risk report command (C3 Week 3, Step 3; decisions D8 and D9)."""

import csv
import json
import re
from pathlib import Path

from app.correlation.report import buckets, distribution, main

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "correlation"
SAMPLE = ROOT / "fixtures" / "ingest" / "unsw-nb15-sample.csv"
IP = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def run(tmp_path, *args):
    out = tmp_path / "report"
    assert main([*args, "--out", str(out), "--now", "2026-01-16T00:00:00+00:00"]) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    with (out / "incidents.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return out, report, rows


def test_fixture_report_matches_the_expected_risk(tmp_path):
    out, report, rows = run(
        tmp_path,
        "fixture",
        str(FIXTURES / "events.json"),
        "--assets",
        str(FIXTURES / "assets.toml"),
    )
    expected = json.loads((FIXTURES / "expected-risk.json").read_text(encoding="utf-8"))
    assert report["incidents"] == len(expected["incidents"]) == len(rows)
    assert report["correlation_config_version"] == "correlation-v2"
    assert report["input"]["events"] == 43 and report["input"]["flagged"] == 24
    levels = {}
    for item in expected["incidents"]:
        levels[item["level"]] = levels.get(item["level"], 0) + 1
    assert report["risk"]["levels"] == levels
    assert sorted(int(r["score"]) for r in rows) == sorted(
        i["score"] for i in expected["incidents"]
    )
    assert report["splits"]["parts"] == 0
    assert sum(report["sizes"]["buckets"].values()) == report["incidents"]


def test_report_never_writes_an_address(tmp_path):
    out, _, _ = run(tmp_path, "fixture", str(FIXTURES / "events.json"))
    for name in ("report.json", "incidents.csv"):
        assert not IP.search((out / name).read_text(encoding="utf-8")), name


def test_unsw_sample_runs_end_to_end(tmp_path):
    out, report, rows = run(tmp_path, "unsw-nb15", str(SAMPLE))
    assert report["dataset_id"] == "unsw-nb15"
    assert report["input"]["flagged"] == 13
    assert report["incidents"] == len(rows) >= 1
    assert not IP.search((out / "incidents.csv").read_text(encoding="utf-8"))


def test_distribution_and_buckets():
    assert distribution([]) == {
        "count": 0, "min": None, "p50": None, "p90": None, "p99": None, "max": None
    }  # fmt: skip
    d = distribution([1, 2, 3, 4, 100])
    assert (d["min"], d["p50"], d["max"]) == (1, 3, 100)
    assert buckets([1, 5, 500, 501])["over 500"] == 1
    assert buckets([1, 5, 500, 501])["500"] == 1
