"""Indicative grouping metrics on one dataset file (C2-D14 to D16; design §14).

    python -m app.evaluation.cli unsw-nb15 <path>/UNSW-NB15_1.csv --out evaluation

Parses the file with C2's parser (two passes, as `app.correlation.report`), correlates it once
per window, builds the ground truth once per gap, and writes counts only: `evaluation.json` and
`evaluation.md`. Nothing written holds an IP address, host or user name.

Windows: the base window w and the escalated window 2w (the shipped 15/30 minutes keep that
ratio, design §4). "As built" scores the incidents with the size cap; "before the cap" joins
the parts of each split group again, so the cap's effect on recall shows separately.
"""

import argparse
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.api.schemas import DatasetSource
from app.contracts import EventRole
from app.correlation.config import load_config
from app.correlation.engine import correlate
from app.correlation.report import load_events
from app.evaluation.ground_truth import ground_truth_incidents
from app.evaluation.metrics import grouping_metrics
from app.ingest.registry import PARSERS

DEFAULT_WINDOWS = (5, 10, 15, 30, 60)
DEFAULT_GAPS = (15, 60, 240)
SHIPPED_WINDOW, DEFAULT_GAP = 15, 60
FIXED_NOW = datetime(2000, 1, 1, tzinfo=UTC)  # incident IDs and metrics never depend on it


def predicted_maps(incidents) -> tuple[dict[str, str], dict[str, str]]:
    """Flagged event -> incident ID, as built and with split parts joined again."""
    built: dict[str, str] = {}
    joined: dict[str, str] = {}
    for incident in incidents:
        group = incident.split.group_id if incident.split else incident.incident_id
        for link in incident.events:
            if link.role == EventRole.FLAGGED:
                built[link.event_id] = incident.incident_id
                joined[link.event_id] = group
    return built, joined


def _round(metrics: dict[str, Any]) -> dict[str, Any]:
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()}


def run(
    dataset_id: DatasetSource,
    path: Path,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    gaps: tuple[int, ...] = DEFAULT_GAPS,
) -> dict[str, Any]:
    base = load_config()
    started = time.perf_counter()
    events, info = load_events(dataset_id, path, base)
    loaded = time.perf_counter()
    truths = {g: ground_truth_incidents(events, timedelta(minutes=g)) for g in gaps}
    rows = []
    for w in windows:
        config = replace(
            base, window=timedelta(minutes=w), escalated_window=timedelta(minutes=2 * w)
        )
        t0 = time.perf_counter()
        result = correlate(events, config, FIXED_NOW)
        seconds = round(time.perf_counter() - t0, 1)
        built, joined = predicted_maps(result.incidents)
        for g, truth in truths.items():
            for variant, predicted in (("as_built", built), ("before_cap", joined)):
                rows.append(
                    {
                        "window_minutes": w,
                        "escalated_window_minutes": 2 * w,
                        "gt_gap_minutes": g,
                        "predicted": variant,
                        "correlate_seconds": seconds,
                        **_round(grouping_metrics(predicted, truth).as_dict()),
                    }
                )
    return {
        "dataset_id": dataset_id.value,
        "file": path.name,
        "bytes": path.stat().st_size,
        "correlation_config_version": base.config_version,
        "size_cap": base.max_incident_events,
        "input": info,
        "ground_truth_rule": "same attack category, attacker IP and victim IP; "
        "consecutive records at most the gap apart (C2-D14)",
        "label": "indicative",
        "rows": rows,
        "seconds_read_two_passes": round(loaded - started, 1),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def markdown(report: dict[str, Any]) -> str:
    cols = (
        "window_minutes", "gt_gap_minutes", "predicted", "incidents", "truth_incidents",
        "precision", "recall", "f1", "incorrect_merges", "missed_groups", "alert_compression",
    )  # fmt: skip
    head = ["Window (min)", "GT gap (min)", "Predicted", "Incidents", "GT incidents",
            "Precision", "Recall", "F1", "Incorrect merges", "Missed groups",
            "Alert compression"]  # fmt: skip
    inp = report["input"]
    lines = [
        f"# Indicative grouping metrics: {report['file']}",
        "",
        f"{inp['events']:,} events, {inp['flagged']:,} flagged, {inp['first_event_at']} to "
        f"{inp['last_event_at']}. {report['correlation_config_version']}, size cap "
        f"{report['size_cap']}. Ground truth: {report['ground_truth_rule']}. "
        "All numbers are **indicative**.",
        "",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    for row in report["rows"]:
        lines.append("| " + " | ".join(_fmt(row[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def _ints(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split(",") if part.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation.cli", description=__doc__)
    parser.add_argument("dataset_id", choices=sorted(source.value for source in PARSERS))
    parser.add_argument("file", type=Path)
    parser.add_argument("--out", type=Path, default=Path("evaluation"))
    parser.add_argument("--windows", type=_ints, default=DEFAULT_WINDOWS, help="e.g. 5,15,60")
    parser.add_argument("--gaps", type=_ints, default=DEFAULT_GAPS, help="GT gaps, e.g. 60")
    args = parser.parse_args(argv)
    report = run(DatasetSource(args.dataset_id), args.file, args.windows, args.gaps)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    (args.out / "evaluation.md").write_text(markdown(report), "utf-8")
    for row in report["rows"]:
        if row["window_minutes"] == SHIPPED_WINDOW and row["gt_gap_minutes"] == DEFAULT_GAP:
            print(
                f"window {SHIPPED_WINDOW}, GT gap {DEFAULT_GAP}, {row['predicted']}: "
                f"P {_fmt(row['precision'])} R {_fmt(row['recall'])} F1 {_fmt(row['f1'])}, "
                f"{row['incidents']:,} incidents vs {row['truth_incidents']:,} GT incidents"
            )
    print(f"wrote {args.out / 'evaluation.json'} and {args.out / 'evaluation.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
