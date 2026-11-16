"""Correlation and risk report on one dataset file (C3 Week 3, Step 3; decisions D8 and D9).

    python -m app.correlation.report unsw-nb15 <path>/UNSW-NB15_1.csv --out correlation-report

Parses the file with C2's parser, correlates (with the size cap), scores every incident and
writes counts only: `report.json` (size distribution, splits, over-merge markers, risk levels)
and `incidents.csv` (one row per incident). No database is needed.

Nothing written holds an IP address, host or user name: the files can be shared with the team.
Incident IDs are hashes, attack types are the dataset's labels.

Memory: the file is read twice. The first pass keeps only the flagged events; the second keeps
only the other events that share a key value with a flagged event, because no other event can
become context (the same rule as `app.incidents.store`).
"""

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.api.schemas import DatasetSource
from app.contracts import Event, EventRole, Incident, LabelStatus
from app.correlation.config import load_config
from app.correlation.engine import correlate
from app.correlation.keys import key_values
from app.correlation.risk import DEFAULT_RISK_CONFIG_PATH, load_risk_config, score_incidents
from app.ingest.interface import IntakeContext
from app.ingest.registry import PARSERS

# Over-merge markers (D8): report only, never an automatic change.
LONG_INCIDENT_MINUTES = 120
MANY_ATTACK_TYPES = 4
SMALL_PART = 10  # a split part with fewer links is counted as a small leftover
SIZE_BUCKETS = ((1, 1), (2, 9), (10, 49), (50, 99), (100, 249), (250, 499), (500, 500))


def _events(dataset_id: DatasetSource, path: Path) -> Iterable[Event]:
    context = IntakeContext(
        upload_id="upl-report",
        dataset_id=dataset_id.value,
        source_file=path.name,
        ingested_at=datetime(2000, 1, 1, tzinfo=UTC),  # fixed: the output never depends on it
    )
    for item in PARSERS[dataset_id](path, context):
        if isinstance(item, Event):
            yield item


def load_events(dataset_id: DatasetSource, path: Path, config) -> tuple[list[Event], dict]:
    """Flagged events plus the others that can become context, and counts of the whole file."""
    counts: Counter[str] = Counter()
    flagged: list[Event] = []
    first = last = None
    for event in _events(dataset_id, path):
        counts[event.label.status.value] += 1
        first = event.timestamp if first is None else min(first, event.timestamp)
        last = event.timestamp if last is None else max(last, event.timestamp)
        if event.label.status == LabelStatus.FLAGGED:
            flagged.append(event)
    wanted = {value for event in flagged for value in key_values(event, config)}
    context = [
        event
        for event in _events(dataset_id, path)
        if event.label.status != LabelStatus.FLAGGED
        and not wanted.isdisjoint(key_values(event, config))
    ]
    info = {
        "events": sum(counts.values()),
        "flagged": counts[LabelStatus.FLAGGED.value],
        "unflagged": counts[LabelStatus.UNFLAGGED.value],
        "unlabelled": counts[LabelStatus.UNLABELLED.value],
        "context_candidates": len(context),
        "first_event_at": first.isoformat() if first else None,
        "last_event_at": last.isoformat() if last else None,
    }
    return flagged + context, info


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "p90": None, "p99": None, "max": None}
    ordered = sorted(values)

    def pct(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(p * len(ordered)))]

    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": pct(0.50),
        "p90": pct(0.90),
        "p99": pct(0.99),
        "max": ordered[-1],
        "mean": round(statistics.fmean(ordered), 2),
    }


def buckets(sizes: list[int]) -> dict[str, int]:
    out = {(f"{lo}" if lo == hi else f"{lo}-{hi}"): 0 for lo, hi in SIZE_BUCKETS}
    out[f"over {SIZE_BUCKETS[-1][1]}"] = 0
    for size in sizes:
        for lo, hi in SIZE_BUCKETS:
            if lo <= size <= hi:
                out[f"{lo}" if lo == hi else f"{lo}-{hi}"] += 1
                break
        else:
            out[f"over {SIZE_BUCKETS[-1][1]}"] += 1
    return out


def _row(incident: Incident, by_id: dict[str, Event], cap: int | None) -> dict[str, Any]:
    flagged = [by_id[link.event_id] for link in incident.events if link.role == EventRole.FLAGGED]
    types = Counter(e.label.attack_type or "unknown" for e in flagged)
    minutes = (incident.last_event_at - incident.first_event_at).total_seconds() / 60
    markers = []
    if cap is not None and len(incident.events) > cap:
        markers.append("over_cap")
    if minutes > LONG_INCIDENT_MINUTES:
        markers.append("long")
    if len(types) >= MANY_ATTACK_TYPES:
        markers.append("many_types")
    risk = incident.risk
    return {
        "incident_id": incident.incident_id,
        "group_id": incident.split.group_id if incident.split else incident.incident_id,
        "part": incident.split.part if incident.split else 1,
        "parts": incident.split.parts if incident.split else 1,
        "gap_seconds": incident.split.gap_seconds if incident.split else None,
        "links": len(incident.events),
        "flagged": len(flagged),
        "context": len(incident.events) - len(flagged),
        "first_event_at": incident.first_event_at.isoformat(),
        "last_event_at": incident.last_event_at.isoformat(),
        "minutes": round(minutes, 2),
        "incident_type": incident.incident_type,
        "attack_types": ";".join(f"{t}:{n}" for t, n in sorted(types.items())),
        "attack_type_count": len(types),
        "score": risk.score if risk else None,
        "level": risk.level.value if risk else None,
        "likelihood": risk.likelihood if risk else None,
        "impact": risk.impact if risk else None,
        "flags": ";".join(f.value for f in risk.flags) if risk else "",
        "markers": ";".join(markers),
    }


def build_report(rows: list[dict[str, Any]], cap: int | None) -> dict[str, Any]:
    sizes = [r["links"] for r in rows]
    group_sizes = Counter()
    for r in rows:
        group_sizes[r["group_id"]] += r["links"]
    split_rows = [r for r in rows if r["parts"] > 1]
    markers = Counter(m for r in rows for m in r["markers"].split(";") if m)
    biggest = sorted(rows, key=lambda r: (-r["links"], r["incident_id"]))[:20]
    return {
        "incidents": len(rows),
        "groups_before_cap": len(group_sizes),
        "size_cap": cap,
        "sizes": {
            "links": distribution(sizes),
            "flagged": distribution([r["flagged"] for r in rows]),
            "context": distribution([r["context"] for r in rows]),
            "buckets": buckets(sizes),
        },
        "groups_before_cap_sizes": {
            "links": distribution(list(group_sizes.values())),
            "buckets": buckets(list(group_sizes.values())),
        },
        "minutes": distribution([r["minutes"] for r in rows]),
        "attack_types_per_incident": dict(
            sorted(Counter(r["attack_type_count"] for r in rows).items())
        ),
        "incident_types": dict(Counter(r["incident_type"] or "none" for r in rows).most_common()),
        "splits": {
            "groups_split": len({r["group_id"] for r in split_rows}),
            "parts": len(split_rows),
            "small_parts": sum(1 for r in split_rows if r["links"] < SMALL_PART),
            "gap_seconds": distribution([r["gap_seconds"] for r in split_rows if r["part"] > 1]),
        },
        "over_merge_markers": {
            "rule": f"over_cap: more than the cap and one flagged event (cannot be cut); "
            f"long: longer than {LONG_INCIDENT_MINUTES} min; many_types: "
            f"{MANY_ATTACK_TYPES} or more attack types",
            "counts": dict(sorted(markers.items())),
            "incidents_with_any": sum(1 for r in rows if r["markers"]),
        },
        "risk": {
            "levels": dict(Counter(r["level"] or "none" for r in rows).most_common()),
            "scores": distribution([r["score"] for r in rows if r["score"] is not None]),
            "flags": dict(
                Counter(f for r in rows for f in r["flags"].split(";") if f).most_common()
            ),
            "likelihood": distribution(
                [r["likelihood"] for r in rows if r["likelihood"] is not None]
            ),
            "impact": distribution([r["impact"] for r in rows if r["impact"] is not None]),
        },
        "largest_incidents": [
            {
                k: r[k]
                for k in (
                    "incident_id",
                    "links",
                    "flagged",
                    "minutes",
                    "attack_types",
                    "level",
                    "markers",
                )
            }
            for r in biggest
        ],
    }


def _peak_memory_mb() -> int | None:
    try:
        import resource  # not on Windows
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024))


def run(
    dataset_id: DatasetSource, path: Path, assets: Path | None, evaluated_at: datetime
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = load_config()
    started = time.perf_counter()
    events, info = load_events(dataset_id, path, config)
    loaded = time.perf_counter()
    result = correlate(events, config, evaluated_at)
    correlated = time.perf_counter()
    risk = load_risk_config(DEFAULT_RISK_CONFIG_PATH, assets)
    last = datetime.fromisoformat(info["last_event_at"]) if info["last_event_at"] else None
    incidents = score_incidents(
        result.incidents, events, evaluated_at, risk, config, reference=last
    )
    scored = time.perf_counter()
    by_id = {e.event_id: e for e in events}
    rows = [_row(i, by_id, config.max_incident_events) for i in incidents]
    linked_context = sum(r["context"] for r in rows)
    report = {
        "dataset_id": dataset_id.value,
        "file": path.name,
        "bytes": path.stat().st_size,
        "correlation_config_version": result.config_version,
        "risk_config_version": risk.config_version,
        "assets_file": assets.name if assets else None,
        "input": {**info, "context_linked": linked_context,
                  "unflagged_or_unlabelled_outside_incidents":
                      info["unflagged"] + info["unlabelled"] - linked_context},
        **build_report(rows, config.max_incident_events),
        "seconds": {
            "read_two_passes": round(loaded - started, 1),
            "correlate": round(correlated - loaded, 1),
            "score": round(scored - correlated, 1),
        },
        "peak_memory_mb": _peak_memory_mb(),
    }  # fmt: skip
    return report, rows


def _print(report: dict[str, Any]) -> None:
    inp, sizes, risk = report["input"], report["sizes"], report["risk"]
    lines = [
        f"{report['file']}: {inp['events']:,} events ({inp['flagged']:,} flagged), "
        f"{inp['first_event_at']} to {inp['last_event_at']}",
        f"{report['correlation_config_version']}, {report['risk_config_version']}, "
        f"cap {report['size_cap']}",
        f"groups before the cap: {report['groups_before_cap']:,}; incidents: "
        f"{report['incidents']:,}; split groups: {report['splits']['groups_split']:,} into "
        f"{report['splits']['parts']:,} parts ({report['splits']['small_parts']:,} small parts)",
        f"size (links): {sizes['links']}",
        f"size buckets: {sizes['buckets']}",
        f"group sizes before the cap: {report['groups_before_cap_sizes']['buckets']}",
        f"minutes: {report['minutes']}",
        f"attack types per incident: {report['attack_types_per_incident']}",
        f"over-merge markers: {report['over_merge_markers']['counts']}",
        f"risk levels: {risk['levels']}; flags: {risk['flags']}",
        f"context linked: {inp['context_linked']:,}; other events outside incidents: "
        f"{inp['unflagged_or_unlabelled_outside_incidents']:,}",
        f"seconds: {report['seconds']}; peak memory: {report['peak_memory_mb']} MB",
    ]
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.correlation.report", description=__doc__)
    parser.add_argument("dataset_id", choices=sorted(source.value for source in PARSERS))
    parser.add_argument("file", type=Path)
    parser.add_argument("--out", type=Path, default=Path("correlation-report"))
    parser.add_argument("--assets", type=Path, help="asset levels TOML (default: none rated)")
    parser.add_argument(
        "--now", help="created_at of the incidents, ISO 8601 UTC (default: the current time)"
    )
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    report, rows = run(DatasetSource(args.dataset_id), args.file, args.assets, now)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with (args.out / "incidents.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["incident_id"])
        writer.writeheader()
        writer.writerows(rows)
    _print(report)
    print(f"wrote {args.out / 'report.json'} and {args.out / 'incidents.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
