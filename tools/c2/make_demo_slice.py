"""Demo dataset slice of UNSW-NB15 (C2, Week 4; decisions C2-D17 and C2-D18).

Choose a new slice from the official file (writes the slice and its manifest):

    python tools/c2/make_demo_slice.py choose <path>/UNSW-NB15_1.csv --out demo/

Rebuild the committed slice and check it byte for byte:

    python tools/c2/make_demo_slice.py rebuild <path>/UNSW-NB15_1.csv --out demo/

The slice is every line of the source file whose event time (`Stime`) lies in one closed range
[start, end], in file order, unchanged. "choose" picks the shortest such range that, uploaded on
its own, gives at least one High and one Medium incident, with at most --max-rows lines; ties
go to the earliest range. Every candidate is checked by correlating and scoring the slice
itself, as the upload job does.

The slice holds dataset rows and is never committed (fixtures/ingest/README.md). Committed:
the manifest fixtures/demo/unsw-nb15-demo-slice.json (source and slice SHA-256, time range,
counts, expected incidents) and fixtures/demo/unsw-nb15-demo-slice.sha256. The manifest holds
no IP address, host or user name.
"""

import argparse
import bisect
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.api.schemas import DatasetSource  # noqa: E402
from app.contracts import Event  # noqa: E402
from app.correlation import report  # noqa: E402
from app.ingest.interface import IntakeContext  # noqa: E402
from app.ingest.registry import PARSERS  # noqa: E402

MANIFEST = REPO / "fixtures" / "demo" / "unsw-nb15-demo-slice.json"
CHECKSUM = REPO / "fixtures" / "demo" / "unsw-nb15-demo-slice.sha256"
SLICE_NAME = "unsw-nb15-demo-slice.csv"
FIXED_NOW = datetime(2000, 1, 1, tzinfo=UTC)
NEIGHBOURS = 25  # High incidents tried per Medium incident, nearest in time
MAX_TRIES = 40


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def line_times(source: Path) -> list[tuple[float, int]]:
    """(event time as epoch seconds, line number) of every parsed event, sorted by time."""
    context = IntakeContext(
        upload_id="upl-slice", dataset_id="unsw-nb15", source_file=source.name,
        ingested_at=FIXED_NOW,
    )  # fmt: skip
    out = []
    for item in PARSERS[DatasetSource.UNSW_NB15](source, context):
        if isinstance(item, Event):
            out.append((item.timestamp.timestamp(), int(item.event_id.rsplit(":", 1)[1])))
    out.sort()
    return out


def write_slice(source: Path, lines: set[int], target: Path) -> int:
    """Copy the chosen lines (1-based) byte for byte, in file order."""
    written = 0
    with source.open("rb") as src, target.open("wb") as dst:
        for number, raw in enumerate(src, start=1):
            if number in lines:
                dst.write(raw)
                written += 1
    return written


def lines_in(times: list[tuple[float, int]], start: float, end: float) -> set[int]:
    lo = bisect.bisect_left(times, (start, -1))
    hi = bisect.bisect_right(times, (end, sys.maxsize))
    return {number for _, number in times[lo:hi]}


def evaluate(path: Path) -> tuple[dict, list[dict]]:
    return report.run(DatasetSource.UNSW_NB15, path, None, FIXED_NOW)


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def candidates(rows: list[dict]) -> list[tuple[float, float, float]]:
    """(span seconds, start, end) of each Medium incident with its nearest High incidents."""
    highs = sorted(
        (_epoch(r["first_event_at"]), _epoch(r["last_event_at"]))
        for r in rows
        if r["level"] == "high"
    )
    starts = [h[0] for h in highs]
    out = set()
    for r in rows:
        if r["level"] != "medium":
            continue
        m0, m1 = _epoch(r["first_event_at"]), _epoch(r["last_event_at"])
        pos = bisect.bisect_left(starts, m0)
        for h0, h1 in highs[max(0, pos - NEIGHBOURS) : pos + NEIGHBOURS]:
            start, end = min(m0, h0), max(m1, h1)
            out.add((end - start, start, end))
    return sorted(out)


def summary(slice_report: dict, rows: list[dict]) -> dict:
    return {
        "events": slice_report["input"]["events"],
        "flagged": slice_report["input"]["flagged"],
        "unflagged": slice_report["input"]["unflagged"],
        "unlabelled": slice_report["input"]["unlabelled"],
        "incidents": len(rows),
        "levels": dict(sorted(Counter(r["level"] for r in rows).items())),
        "correlation_config_version": slice_report["correlation_config_version"],
        "risk_config_version": slice_report["risk_config_version"],
        "expected_incidents": [
            {
                k: r[k]
                for k in (
                    "incident_id",
                    "level",
                    "score",
                    "flagged",
                    "context",
                    "minutes",
                    "incident_type",
                    "attack_types",
                )
            }
            for r in sorted(rows, key=lambda r: (r["first_event_at"], r["incident_id"]))
        ],  # fmt: skip
    }


def choose(source: Path, out: Path, max_rows: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    full_report, full_rows = evaluate(source)
    levels = Counter(r["level"] for r in full_rows)
    print(f"{source.name}: {len(full_rows):,} incidents on the whole file; levels {dict(levels)}")
    times = line_times(source)
    target = out / SLICE_NAME
    tried = 0
    for span, start, end in candidates(full_rows):
        lines = lines_in(times, start, end)
        if len(lines) > max_rows:
            continue
        tried += 1
        write_slice(source, lines, target)
        slice_report, rows = evaluate(target)
        got = Counter(r["level"] for r in rows)
        print(f"  try {tried}: {len(lines):,} lines, {span / 60:.1f} min, levels {dict(got)}")
        if got["high"] >= 1 and got["medium"] >= 1:
            manifest = {
                "source": {
                    "dataset_id": "unsw-nb15",
                    "file": source.name,
                    "bytes": source.stat().st_size,
                    "sha256": sha256(source),
                    "where": "official UNSW-NB15 folder 'CSV Files' (tools/c2/unsw_download.py)",
                },
                "rule": "every line whose Stime is in [start, end] (epoch seconds, inclusive), "
                "in file order, unchanged (C2-D17)",
                "start_epoch": start,
                "end_epoch": end,
                "start_utc": datetime.fromtimestamp(start, UTC).isoformat(),
                "end_utc": datetime.fromtimestamp(end, UTC).isoformat(),
                "lines": len(lines),
                "first_line": min(lines),
                "last_line": max(lines),
                "slice_file": SLICE_NAME,
                "slice_bytes": target.stat().st_size,
                "slice_sha256": sha256(target),
                **summary(slice_report, rows),
            }
            (out / MANIFEST.name).write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
            (out / CHECKSUM.name).write_text(f"{manifest['slice_sha256']}  {SLICE_NAME}\n")
            print(f"chosen: {len(lines):,} lines, sha256 {manifest['slice_sha256']}")
            print(json.dumps({k: v for k, v in manifest.items() if k != "expected_incidents"}))
            return 0
        if tried >= MAX_TRIES:
            break
    print(f"no range with a High and a Medium incident in {tried} tries", file=sys.stderr)
    return 1


def rebuild(source: Path, out: Path, manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    got = sha256(source)
    if got != manifest["source"]["sha256"]:
        print(f"source differs: sha256 {got}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    target = out / manifest["slice_file"]
    lines = lines_in(line_times(source), manifest["start_epoch"], manifest["end_epoch"])
    write_slice(source, lines, target)
    digest = sha256(target)
    ok = digest == manifest["slice_sha256"] and len(lines) == manifest["lines"]
    print(f"{target}: {len(lines):,} lines, sha256 {digest} ({'matches' if ok else 'DIFFERS'})")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("choose", "rebuild"))
    parser.add_argument("source", type=Path, help="the official UNSW-NB15_1.csv")
    parser.add_argument("--out", type=Path, default=Path("demo"))
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    if args.mode == "choose":
        return choose(args.source, args.out, args.max_rows)
    return rebuild(args.source, args.out, args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
