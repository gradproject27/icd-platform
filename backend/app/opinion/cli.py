"""LLM opinion runs (AI1). Run from backend/.

    # 1. Opinions for the incidents of an events file (fixture format: a JSON list of Events)
    python -m app.opinion.cli incidents ../fixtures/correlation/events.json --out ../opinion-run

    # 2. A labelled calibration set from a dataset file, then the model's opinion on each group
    python -m app.opinion.cli label-set unsw-nb15 ../data/UNSW-NB15_1.csv --out ../opinion-cal \
        --groups 200 --max-events 200000

    # 3. Fit the Platt calibrator on those answers and report the measures (out-of-fold)
    python -m app.opinion.cli calibrate ../opinion-cal/results.jsonl --out ../opinion-cal \
        --version cal-unsw1-qwen27b-v1 --source "UNSW-NB15_1, first 200,000 lines, 200 groups"

The model comes from ICD_OPINION_BACKEND (stub by default) and the ICD_LLM_* variables
(app/opinion/client.py). `--cache-dir` re-uses earlier answers. No output holds a masked view or
a prompt; results hold real group keys and stay on the app host, like the masking maps.
"""

import argparse
import hashlib
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
from app.opinion.calibration import Calibrator, cross_validated, fit_platt, measures, reliability
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


def _read_dataset(dataset: str, path: Path, max_events: int | None) -> list[Event]:
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
            events.append(item)
            if max_events is not None and len(events) >= max_events:
                break
    return events


def _rank(group: OpinionGroup) -> str:
    """A fixed pseudo-random order, so the same file always gives the same sample of groups."""
    return hashlib.sha256(
        f"{group.technique}|{group.entity}|{group.events[0].event_id}".encode()
    ).hexdigest()


def balanced_sample(groups: list[OpinionGroup], total: int) -> list[OpinionGroup]:
    """Up to total/2 attack groups and total/2 normal groups (the rest topped up from the other
    class), each chosen in the fixed order of `_rank`."""
    attacks = sorted((g for g in groups if g.truth == 1), key=_rank)
    normal = sorted((g for g in groups if g.truth == 0), key=_rank)
    half = total // 2
    take_a = min(len(attacks), max(half, total - len(normal)))
    take_n = min(len(normal), total - take_a)
    return attacks[:take_a] + normal[:take_n]


def cmd_label_set(args: argparse.Namespace) -> int:
    events = _read_dataset(args.dataset, Path(args.file), args.max_events)
    groups = labelled_groups(events)
    chosen = balanced_sample(groups, args.groups)
    client, settings = client_from_env(), _settings(args)
    cache = _cache(args)
    rows = []
    for i, group in enumerate(chosen, 1):
        opinion = estimate(group, client, settings, None, cache)
        rows.append({"truth": group.truth, "opinion": opinion.model_dump(mode="json")})
        if i % 10 == 0 or i == len(chosen):
            print(f"  {i}/{len(chosen)}", file=sys.stderr)
    out = Path(args.out)
    _write_jsonl(out / "results.jsonl", rows)
    attacks = sum(1 for g in chosen if g.truth == 1)
    print(
        f"{len(events)} events, {len(groups)} labelled groups, {len(chosen)} chosen "
        f"({attacks} attack, {len(chosen) - attacks} normal); "
        f"{_status_line([GroupOpinion.model_validate(r['opinion']) for r in rows])} "
        f"-> {out / 'results.jsonl'}"
    )
    return 0


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def calibration_report(rows: list[dict], calibrator: Calibrator, folds: int) -> dict:
    ok = [(GroupOpinion.model_validate(r["opinion"]), r["truth"]) for r in rows]
    failed = [o for o, _ in ok if o.status != "ok"]
    used = [(o, y) for o, y in ok if o.status == "ok"]
    p_raw = [o.p_raw for o, _ in used]
    truth = [y for _, y in used]
    p_cv = cross_validated(p_raw, truth, folds, calibrator.eps)
    return {
        "calibrator": calibrator.model_dump(mode="json"),
        "rows": len(rows),
        "failed": len(failed),
        "failures": dict(Counter((o.failure or "").split(":")[0] for o in failed)),
        "raw": measures(p_raw, truth),
        "calibrated_out_of_fold": measures(p_cv, truth),
        "folds": folds,
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
        f"- calibrated values are out-of-fold ({report['folds']} folds): no group is scored by "
        "a fit that saw it",
        "",
        "| Measure | Raw | Calibrated (out-of-fold) | Proposed pass mark |",
        "|---|---|---|---|",
    ]
    marks = {"ece": "<= 0.05", "auc": ">= 0.95", "brier": "reported", "log_loss": "reported"}
    for name in ("groups", "attacks", "brier", "log_loss", "ece", "auc"):
        lines.append(
            f"| {name} | {_fmt(report['raw'][name])} | "
            f"{_fmt(report['calibrated_out_of_fold'][name])} | {marks.get(name, '')} |"
        )
    lines += [
        "",
        "The pass marks in design note 9A.2 are for the stacked C, not for the LLM opinion "
        "alone; they are shown for reference.",
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
        for line in Path(args.results).read_text("utf-8").splitlines()
        if line.strip()
    ]
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
    p.add_argument("--groups", type=int, default=200, help="groups to ask about (balanced)")
    p.add_argument("--max-events", type=int, help="read only the first N events")
    _add_model_options(p)
    p.set_defaults(func=cmd_label_set)

    p = sub.add_parser("calibrate", help="fit the Platt calibrator on label-set results")
    p.add_argument("results")
    p.add_argument("--out", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--folds", type=int, default=5)
    p.set_defaults(func=cmd_calibrate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
