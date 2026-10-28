"""Run a dataset parser on a local file and print the intake summary (plan section 5, step 6).

    python -m app.ingest.cli unsw-nb15 D:/data/UNSW-NB15_1.csv
    python -m app.ingest.cli unsw-nb15 D:/data/UNSW-NB15_1.csv --json
    python -m app.ingest.cli unsw-nb15 D:/data/UNSW-NB15_1.csv --profile
    python -m app.ingest.cli unsw-nb15 D:/data/UNSW-NB15_1.csv --show-record UNSW-NB15_1.csv:42

No database is needed: the counts follow the same rules as the ingest worker
(app/jobs/ingest.py), including quarantining a repeated event_id. The summary and the profile
hold counts only, never a record. --show-record prints one original line, which can hold real
IPs: use it on your own screen, not in a chat or an issue.
"""

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.api.schemas import DatasetSource, IntakeCounts
from app.contracts import Event
from app.ingest.interface import IntakeContext, ParseError, Quarantined
from app.ingest.lines import read_original
from app.ingest.registry import PARSERS
from app.ingest.unsw_nb15 import profile


def intake_counts(items: Iterable[Event | Quarantined]) -> IntakeCounts:
    """The intake summary of a parser run, counted like the worker counts it."""
    records_read = 0
    labels: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    seen: set[str] = set()
    for item in items:
        records_read += 1
        if isinstance(item, Event) and item.event_id not in seen:
            seen.add(item.event_id)
            labels[item.label.status.value] += 1
        elif isinstance(item, Event):
            reasons["duplicate_event_id"] += 1
        else:
            reasons[item.reason_code] += 1
    return IntakeCounts(
        records_read=records_read,
        events_stored=sum(labels.values()),
        flagged=labels["flagged"],
        unflagged=labels["unflagged"],
        unlabelled=labels["unlabelled"],
        quarantined=sum(reasons.values()),
        quarantined_by_reason=dict(sorted(reasons.items())),
    )


def run(dataset_id: DatasetSource, path: Path) -> dict[str, Any]:
    context = IntakeContext(
        upload_id="upl-cli",
        dataset_id=dataset_id.value,
        source_file=path.name,
        ingested_at=datetime.now(UTC),
    )
    started = time.perf_counter()
    counts = intake_counts(PARSERS[dataset_id](path, context))
    seconds = time.perf_counter() - started
    return {
        "dataset_id": dataset_id.value,
        "file": path.name,
        "bytes": path.stat().st_size,
        "seconds": round(seconds, 2),
        "records_per_second": round(counts.records_read / seconds) if seconds else None,
        "counts": counts.model_dump(),
    }


def _print_summary(result: dict[str, Any]) -> None:
    counts = result["counts"]
    labelled = counts["flagged"] + counts["unflagged"]
    rows = [
        ("Dataset", result["dataset_id"]),
        ("File", f"{result['file']} ({result['bytes']:,} bytes)"),
        ("Records read", f"{counts['records_read']:,}"),
        ("Normalized (events)", f"{counts['events_stored']:,}"),
        ("  labelled", f"{labelled:,} (flagged {counts['flagged']:,}, "
                       f"unflagged {counts['unflagged']:,})"),
        ("  unlabelled", f"{counts['unlabelled']:,}"),
        ("Quarantined", f"{counts['quarantined']:,}"),
    ]  # fmt: skip
    rows += [(f"  {code}", f"{n:,}") for code, n in counts["quarantined_by_reason"].items()]
    rows += [
        ("Check", "labelled + unlabelled + quarantined = records read"),
        ("Time", f"{result['seconds']} s ({result['records_per_second']:,} records/s)"),
    ]
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        print(f"{name:<{width}}  {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest.cli", description=__doc__)
    parser.add_argument("dataset_id", choices=sorted(source.value for source in PARSERS))
    parser.add_argument("file", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--json", action="store_true", help="print the summary as JSON")
    mode.add_argument("--profile", action="store_true", help="aggregate value counts only")
    mode.add_argument("--show-record", metavar="REF", help="print the original line of REF")
    args = parser.parse_args(argv)

    if not args.file.is_file():
        print(f"error: {args.file} is not a file", file=sys.stderr)
        return 2
    dataset_id = DatasetSource(args.dataset_id)
    if args.show_record:
        print(read_original(args.file, args.show_record))
        return 0
    if args.profile:
        if dataset_id != DatasetSource.UNSW_NB15:
            print("error: --profile supports unsw-nb15 only", file=sys.stderr)
            return 2
        print(json.dumps(profile(args.file), indent=2, ensure_ascii=False))
        return 0
    try:
        result = run(dataset_id, args.file)
    except ParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
