"""LLM opinion runs (AI1). Run from backend/.

    # 1. Opinions for the incidents of an events file (fixture format: a JSON list of Events)
    python -m app.opinion.cli incidents ../fixtures/correlation/events.json --out ../opinion-run

    # 2. A labelled calibration set: one NF-v3 file (or a time range of it) that the classifier
    #    never trains on, groups in their natural attack ratio, and the model's opinion on each
    python -m app.opinion.cli label-set nf-unsw-nb15-v3 ../data/NF-UNSW-NB15-v3.csv \
        --start 2015-02-18 --end 2015-02-19 --groups 400 --out ../opinion-cal/nf-unsw

    # 3. Fit one Platt calibrator on the results of both datasets; measures per dataset, macro
    #    average and pooled, out-of-fold over contiguous time blocks
    python -m app.opinion.cli calibrate ../opinion-cal/nf-unsw/results.jsonl \
        ../opinion-cal/nf-cic/results.jsonl --out ../opinion-cal \
        --version cal-nf-v3-qwen27b-v1 --source "calibration split agreed with C2 and C3"

Data roles (data plan rows 2, 3, 5; RV1-D5, RV1-D10): calibration uses only the NF-v3 versions of
UNSW-NB15 and CSE-CIC-IDS2018, the classifier's datasets. The original UNSW-NB15 CSVs are for the
demo, correlation evaluation and ground truth; Precinct6 is an agreement check only; OTRF events
are unlabelled. Those are refused. `fixture` is accepted for dry runs and tests only.

The model comes from ICD_OPINION_BACKEND (stub by default) and the ICD_LLM_* variables
(app/opinion/client.py). `--cache-dir` re-uses earlier answers. No output holds a masked view or
a prompt; results hold real group keys and stay on the app host, like the masking maps.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.api.schemas import DatasetSource
from app.contracts import Event
from app.correlation import correlate, load_config
from app.ingest.interface import IntakeContext
from app.ingest.registry import PARSERS
from app.opinion.calibration import (
    Calibrator,
    cross_validated,
    fit_platt,
    measures,
    reliability,
    time_blocks,
)
from app.opinion.client import client_from_env
from app.opinion.estimate import (
    FileOpinionCache,
    OpinionCache,
    OpinionSettings,
    estimate,
    estimate_incident,
)
from app.opinion.groups import OpinionGroup, labelled_groups
from app.opinion.models import GroupOpinion


def _settings(args: argparse.Namespace) -> OpinionSettings:
    if args.method == "logprob":
        return OpinionSettings.logprob()
    return OpinionSettings(
        samples=args.samples,
        temperature=args.temperature,
        min_valid=min(args.min_valid, args.samples),
    )


def _cache(args: argparse.Namespace) -> OpinionCache | None:
    return FileOpinionCache(Path(args.cache_dir)) if args.cache_dir else None


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _status_line(opinions: list[GroupOpinion]) -> str:
    counts = Counter(o.status for o in opinions)
    return f"{len(opinions)} groups: {counts.get('ok', 0)} ok, {counts.get('failed', 0)} failed"


def cmd_incidents(args: argparse.Namespace) -> int:
    events = [Event.model_validate(e) for e in json.loads(Path(args.events).read_text("utf-8"))]
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    result = correlate(events, load_config(), now)
    by_id = {e.event_id: e for e in events}
    client, settings = client_from_env(), _settings(args)
    calibrator = Calibrator.load(Path(args.calibrator)) if args.calibrator else None
    opinions = [
        opinion
        for incident in result.incidents
        for opinion in estimate_incident(
            incident, by_id, client, settings, calibrator, _cache(args)
        )
    ]
    out = Path(args.out)
    _write_jsonl(out / "opinions.jsonl", [o.model_dump(mode="json") for o in opinions])
    print(
        f"{len(result.incidents)} incidents, {_status_line(opinions)} -> {out / 'opinions.jsonl'}"
    )
    return 0


CALIBRATION_DATASETS = frozenset({"nf-unsw-nb15-v3", "nf-cse-cic-ids2018-v3"})
DRY_RUN_DATASETS = frozenset({"fixture"})
REFUSED = {
    "unsw-nb15": "the original UNSW-NB15 CSVs are for the demo, correlation evaluation and "
    "ground truth, not training or calibration (data plan row 5, RV1-D10); use nf-unsw-nb15-v3",
    "precinct6": "Precinct6 is an agreement check only, never an input (RV1-D5, CON-20)",
    "otrf": "OTRF events are unlabelled; OTRF is the ATT&CK technique ground truth (RV1-D5)",
}
# Fewer attack groups than this makes the fit and every measure unreliable.
MIN_ATTACK_GROUPS = 30


def check_dataset(dataset: str) -> None:
    if dataset in CALIBRATION_DATASETS or dataset in DRY_RUN_DATASETS:
        return
    reason = REFUSED.get(dataset, "not a calibration dataset of risk-v1 (RV1-D5)")
    raise ValueError(f"{dataset}: {reason}")


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _read_dataset(
    dataset: str,
    path: Path,
    max_events: int | None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Event]:
    """The labelled events of one file, optionally one time range [start, end) of it (a split
    by day, never by random rows), optionally only the first max_events of that range."""
    source = DatasetSource(dataset)
    context = IntakeContext(
        upload_id="upl-opinion",
        dataset_id=source.value,
        source_file=path.name,
        ingested_at=datetime.now(UTC),
    )
    events = []
    for item in PARSERS[source](path, context):
        if isinstance(item, Event):
            if (start and item.timestamp < start) or (end and item.timestamp >= end):
                continue
            events.append(item)
            if max_events is not None and len(events) >= max_events:
                break
    return events


def _start(group: OpinionGroup) -> tuple:
    return (group.events[0].timestamp, group.events[0].event_id)


def _spread(groups: list[OpinionGroup], count: int) -> list[OpinionGroup]:
    """count groups evenly spaced in time, first and last included. Deterministic, no hashing."""
    ordered = sorted(groups, key=_start)
    if count >= len(ordered):
        return ordered
    if count <= 0:
        return []
    if count == 1:
        return [ordered[0]]
    step = (len(ordered) - 1) / (count - 1)
    return [ordered[round(i * step)] for i in range(count)]


def natural_sample(groups: list[OpinionGroup], total: int) -> list[OpinionGroup]:
    """Up to total groups in the split's own attack ratio (RV1-D5: calibration sets keep each
    dataset's natural attack ratio), each class spread evenly over the split's time range."""
    if total >= len(groups):
        return sorted(groups, key=_start)
    attacks = [g for g in groups if g.truth == 1]
    normal = [g for g in groups if g.truth == 0]
    take_a = round(total * len(attacks) / len(groups))
    if attacks and take_a == 0:
        take_a = 1  # keep the class present; the share is reported
    take_n = min(len(normal), total - take_a)
    return sorted(_spread(attacks, take_a) + _spread(normal, take_n), key=_start)


def cmd_label_set(args: argparse.Namespace) -> int:
    try:
        check_dataset(args.dataset)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    start, end = _when(args.start), _when(args.end)
    events = _read_dataset(args.dataset, Path(args.file), args.max_events, start, end)
    split = f"{Path(args.file).name} [{args.start or 'start'}, {args.end or 'end'})" + (
        f", first {args.max_events} events" if args.max_events else ""
    )
    groups = labelled_groups(events)
    if not groups:
        print(f"{split}: no labelled groups", file=sys.stderr)
        return 1
    chosen = natural_sample(groups, args.groups)
    client, settings = client_from_env(), _settings(args)
    cache = _cache(args)
    rows = []
    for i, group in enumerate(chosen, 1):
        opinion = estimate(group, client, settings, None, cache)
        rows.append(
            {
                "dataset": args.dataset,
                "split": split,
                "start": group.events[0].timestamp.isoformat(),
                "truth": group.truth,
                "opinion": opinion.model_dump(mode="json"),
            }
        )
        if i % 10 == 0 or i == len(chosen):
            print(f"  {i}/{len(chosen)}", file=sys.stderr)
    out = Path(args.out)
    _write_jsonl(out / "results.jsonl", rows)
    attacks = sum(1 for g in chosen if g.truth == 1)
    in_split = sum(1 for g in groups if g.truth == 1)
    if attacks < MIN_ATTACK_GROUPS:
        print(
            f"warning: only {attacks} attack groups; at least {MIN_ATTACK_GROUPS} are needed for "
            "a reliable fit. Ask about more groups (--groups) or a longer range.",
            file=sys.stderr,
        )
    print(
        f"{split}: {len(events)} events, {len(groups)} labelled groups "
        f"({in_split / len(groups):.1%} attack), {len(chosen)} chosen "
        f"({attacks} attack, {len(chosen) - attacks} normal); "
        f"{_status_line([GroupOpinion.model_validate(r['opinion']) for r in rows])} "
        f"-> {out / 'results.jsonl'}"
    )
    return 0


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


MACRO_MEASURES = ("brier", "log_loss", "ece", "auc")


def _macro(per_dataset: dict[str, dict]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for name in MACRO_MEASURES:
        values = [m[name] for m in per_dataset.values() if m[name] is not None]
        out[name] = sum(values) / len(values) if values else None
    return out


def calibration_report(rows: list[dict], calibrator: Calibrator, folds: int) -> dict:
    """Raw and out-of-fold calibrated measures: pooled, per dataset and macro (RV1-D5)."""
    parsed = [(r, GroupOpinion.model_validate(r["opinion"])) for r in rows]
    failed = [o for _, o in parsed if o.status != "ok"]
    used = [(r, o) for r, o in parsed if o.status == "ok"]
    datasets = [r["dataset"] for r, _ in used]
    p_raw = [o.p_raw for _, o in used]
    truth = [r["truth"] for r, _ in used]
    fold_of = time_blocks(datasets, [r["start"] for r, _ in used], folds)
    p_cv = cross_validated(p_raw, truth, folds, calibrator.eps, fold_of)

    def part(indices: list[int]) -> dict:
        return {
            "raw": measures([p_raw[i] for i in indices], [truth[i] for i in indices]),
            "calibrated_out_of_fold": measures(
                [p_cv[i] for i in indices], [truth[i] for i in indices]
            ),
        }

    per_dataset = {
        d: part([i for i in range(len(used)) if datasets[i] == d]) for d in sorted(set(datasets))
    }
    return {
        "calibrator": calibrator.model_dump(mode="json"),
        "rows": len(rows),
        "failed": len(failed),
        "failures": dict(Counter((o.failure or "").split(":")[0] for o in failed)),
        "splits": sorted({r["split"] for r, _ in used}),
        "folds": folds,
        "fold_rule": "contiguous time blocks within each dataset",
        "pooled": part(list(range(len(used)))),
        "per_dataset": per_dataset,
        "macro": {
            "raw": _macro({d: v["raw"] for d, v in per_dataset.items()}),
            "calibrated_out_of_fold": _macro(
                {d: v["calibrated_out_of_fold"] for d, v in per_dataset.items()}
            ),
        },
        "reliability_raw": reliability(p_raw, truth),
        "reliability_calibrated_out_of_fold": reliability(p_cv, truth),
    }


def report_markdown(report: dict) -> str:
    cal = report["calibrator"]
    lines = [
        "# LLM opinion calibration",
        "",
        f"- calibrator: `{cal['version']}` (a = {cal['a']:.4f}, b = {cal['b']:.4f})",
        f"- method: {cal['method']}, prompt: {cal['prompt_version']}, model: {cal['model_id']}",
        f"- source: {cal['source']}",
        f"- groups: {report['rows']} ({report['failed']} failed, not used: "
        f"{report['failures'] or 'none'})",
        f"- splits: {'; '.join(report['splits'])}",
        f"- calibrated values are out-of-fold ({report['folds']} folds, "
        f"{report['fold_rule']}): no group is scored by a fit that saw it",
        "",
        "| Set | Groups | Attacks | Brier raw / cal | Log loss raw / cal | ECE raw / cal "
        "| AUC raw / cal |",
        "|---|---|---|---|---|---|---|",
    ]

    def row(name: str, part: dict) -> str:
        raw, cal = part["raw"], part["calibrated_out_of_fold"]
        counts = f"{raw.get('groups', '')} | {raw.get('attacks', '')}"
        cells = " | ".join(f"{_fmt(raw[m])} / {_fmt(cal[m])}" for m in MACRO_MEASURES)
        return f"| {name} | {counts} | {cells} |"

    for dataset, part in report["per_dataset"].items():
        lines.append(row(dataset, part))
    lines.append(row("macro average", report["macro"]))
    lines.append(row("pooled", report["pooled"]))
    lines += [
        "",
        "Every set keeps its dataset's natural attack ratio (RV1-D5). Proposed pass marks "
        "(design note 9A.2, for the stacked C, shown for reference): ECE <= 0.05, AUC >= 0.95.",
        "",
        "## Reliability (calibrated, out-of-fold)",
        "",
        "| Bin | Groups | Mean predicted | Attack share |",
        "|---|---|---|---|",
    ]
    for row in report["reliability_calibrated_out_of_fold"]:
        lines.append(
            f"| {row['bin_low']:.1f} to {row['bin_high']:.1f} | {row['count']} | "
            f"{row['mean_predicted']:.3f} | {row['attack_share']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def cmd_calibrate(args: argparse.Namespace) -> int:
    rows = [
        json.loads(line)
        for path in args.results
        for line in Path(path).read_text("utf-8").splitlines()
        if line.strip()
    ]
    if any("dataset" not in r or "start" not in r for r in rows):
        print("results without dataset or start: run label-set again", file=sys.stderr)
        return 1
    try:
        for dataset in sorted({r["dataset"] for r in rows}):
            check_dataset(dataset)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    used = [(GroupOpinion.model_validate(r["opinion"]), r["truth"]) for r in rows]
    used = [(o, y) for o, y in used if o.status == "ok"]
    if not used:
        print("no ok opinions to calibrate on", file=sys.stderr)
        return 1
    setups = {(o.method, o.prompt_version, o.model_id) for o, _ in used}
    if len(setups) != 1:
        print(f"results mix setups {sorted(setups)}; calibrate one at a time", file=sys.stderr)
        return 1
    method, prompt_version, model_id = setups.pop()
    p_raw, truth = [o.p_raw for o, _ in used], [y for _, y in used]
    a, b = fit_platt(p_raw, truth)
    calibrator = Calibrator(
        version=args.version,
        method=method,
        prompt_version=prompt_version,
        model_id=model_id,
        a=a,
        b=b,
        fitted_on=len(used),
        positives=sum(truth),
        source=args.source,
        fitted_at=datetime.now(UTC),
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    calibrator.save(out / "calibrator.json")
    report = calibration_report(rows, calibrator, args.folds)
    (out / "calibration.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / "calibration.md").write_text(report_markdown(report), encoding="utf-8")
    print(f"a = {a:.4f}, b = {b:.4f} on {len(used)} groups -> {out / 'calibrator.json'}")
    return 0


def _add_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--method", choices=["samples", "logprob"], default="samples")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--min-valid", type=int, default=3)
    parser.add_argument("--cache-dir", help="re-use answers stored here")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.opinion.cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("incidents", help="opinions for the incidents of an events file")
    p.add_argument("events", help="JSON list of Events (fixture format)")
    p.add_argument("--out", required=True)
    p.add_argument("--now", help="correlation time, ISO 8601 (default: now)")
    p.add_argument("--calibrator", help="calibrator.json; without it p_llm stays null")
    _add_model_options(p)
    p.set_defaults(func=cmd_incidents)

    p = sub.add_parser("label-set", help="labelled groups from a dataset file, with opinions")
    p.add_argument("dataset", choices=[s.value for s in PARSERS])
    p.add_argument("file")
    p.add_argument("--out", required=True)
    p.add_argument(
        "--groups", type=int, default=400, help="groups to ask about, in the natural ratio"
    )
    p.add_argument("--start", help="split: first event time, ISO (e.g. 2015-02-18)")
    p.add_argument("--end", help="split: end of the range, exclusive")
    p.add_argument("--max-events", type=int, help="read only the first N events of the range")
    _add_model_options(p)
    p.set_defaults(func=cmd_label_set)

    p = sub.add_parser("calibrate", help="fit the Platt calibrator on label-set results")
    p.add_argument("results", nargs="+", help="results.jsonl of one or more label-set runs")
    p.add_argument("--out", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--folds", type=int, default=5)
    p.set_defaults(func=cmd_calibrate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
