"""Indicative grouping metrics and the UNSW-NB15 ground-truth rule (C2-D14 to D16)."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.contracts import Event
from app.evaluation.cli import main
from app.evaluation.ground_truth import ground_truth_incidents
from app.evaluation.metrics import grouping_metrics

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "fixtures" / "ingest" / "unsw-nb15-sample.csv"
IP = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
T0 = datetime(2015, 1, 22, 11, 0, tzinfo=UTC)


def ev(n, minutes, attack="Exploits", src="192.0.2.1", dst="198.51.100.1", status="flagged"):
    raw = {"flagged": "1", "unflagged": "0"}[status]
    return Event.model_validate(
        {
            "event_id": f"t-{n:03d}",
            "timestamp": (T0 + timedelta(minutes=minutes)).isoformat(),
            "ingested_at": T0.isoformat(),
            "event_type": "unknown",
            "label": {
                "status": status,
                "raw_value": raw,
                "attack_type": attack if status == "flagged" else None,
            },
            "summary": "test event",
            "src_ip": src,
            "dst_ip": dst,
            "provenance": {
                "dataset_id": "test",
                "source_file": "test.csv",
                "record_ref": str(n),
                "source_format": "csv",
            },
        }
    )


# --- metrics: the worked example of design §14.2 and §14.3 ----------------------------------


def test_worked_example_of_the_design():
    truth = {"e1": "G1", "e2": "G1", "e3": "G1", "e4": "G2", "e5": "G2"}
    predicted = {"e1": "I1", "e2": "I1", "e3": "I2", "e4": "I2", "e5": "I2"}
    m = grouping_metrics(predicted, truth)
    assert (m.tp, m.fp, m.fn) == (2, 2, 2)
    assert m.precision == m.recall == m.f1 == 0.5
    assert m.incorrect_merges == 1 and m.missed_groups == 1
    assert m.alert_compression == 2.5
    assert (m.incidents, m.truth_incidents, m.flagged_events) == (2, 2, 5)


def test_perfect_grouping():
    truth = {"a": "G1", "b": "G1", "c": "G2"}
    m = grouping_metrics({"a": "x", "b": "x", "c": "y"}, truth)
    assert (m.precision, m.recall, m.f1) == (1.0, 1.0, 1.0)
    assert m.incorrect_merges == m.missed_groups == 0


def test_all_singletons_have_no_predicted_pairs():
    m = grouping_metrics({"a": "1", "b": "2"}, {"a": "G", "b": "G"})
    assert m.precision is None and m.recall == 0.0 and m.f1 is None
    assert m.missed_groups == 1


def test_event_sets_must_match():
    with pytest.raises(ValueError, match="event sets differ"):
        grouping_metrics({"a": "1"}, {"a": "G", "b": "G"})


def test_pair_counts_match_brute_force():
    import itertools
    import random

    rng = random.Random(7)
    ids = [f"e{i}" for i in range(60)]
    predicted = {e: f"I{rng.randrange(8)}" for e in ids}
    truth = {e: f"G{rng.randrange(6)}" for e in ids}
    tp = fp = fn = 0
    for a, b in itertools.combinations(ids, 2):
        p, t = predicted[a] == predicted[b], truth[a] == truth[b]
        tp += p and t
        fp += p and not t
        fn += t and not p
    m = grouping_metrics(predicted, truth)
    assert (m.tp, m.fp, m.fn) == (tp, fp, fn)


# --- the ground-truth rule (C2-D14) ---------------------------------------------------------


def test_same_category_attacker_and_victim_within_the_gap_is_one_incident():
    events = [ev(1, 0), ev(2, 50), ev(3, 110)]  # 50 and 60 minutes apart: chained
    assert len(set(ground_truth_incidents(events).values())) == 1


def test_a_gap_over_the_limit_starts_a_new_incident():
    events = [ev(1, 0), ev(2, 61)]
    truth = ground_truth_incidents(events)
    assert truth == {"t-001": "gt-1", "t-002": "gt-2"}
    assert len(set(ground_truth_incidents(events, timedelta(minutes=240)).values())) == 1


def test_category_attacker_and_victim_each_separate_incidents():
    events = [
        ev(1, 0),
        ev(2, 1, attack="DoS"),
        ev(3, 2, src="192.0.2.2"),
        ev(4, 3, dst="198.51.100.2"),
        ev(5, 4, attack="Backdoors"),
        ev(6, 5, attack="Backdoor"),  # spelling variants are not merged (C2 decision D5)
    ]
    assert len(set(ground_truth_incidents(events).values())) == 6


def test_unflagged_events_are_not_in_the_ground_truth():
    truth = ground_truth_incidents([ev(1, 0), ev(2, 1, status="unflagged")])
    assert list(truth) == ["t-001"]


def test_ground_truth_ids_are_numbered_by_start_and_reproducible():
    events = [ev(3, 30, attack="DoS"), ev(1, 0), ev(2, 10, src="192.0.2.9")]
    first = ground_truth_incidents(events)
    assert first == {"t-001": "gt-1", "t-002": "gt-2", "t-003": "gt-3"}
    assert ground_truth_incidents(list(reversed(events))) == first


# --- the command ----------------------------------------------------------------------------


def test_cli_on_the_unsw_sample_writes_counts_only(tmp_path):
    out = tmp_path / "evaluation"
    assert main(["unsw-nb15", str(SAMPLE), "--out", str(out), "--windows", "5,15"]) == 0
    report = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert report["label"] == "indicative"
    assert report["input"]["flagged"] == 13
    # 2 windows x 3 GT gaps x (as built, before the cap)
    assert len(report["rows"]) == 12
    for row in report["rows"]:
        assert row["flagged_events"] == 13
        assert row["precision"] is None or 0 <= row["precision"] <= 1
    for name in ("evaluation.json", "evaluation.md"):
        assert not IP.search((out / name).read_text(encoding="utf-8")), name
