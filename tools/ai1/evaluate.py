"""Score a bench run folder against the five AI1 test incidents (evaluation metrics v1).

    python tools/ai1/bench.py --backend openai_http ... \
        --packages fixtures/ai1/packages/*.json --runs 3 --out tools/ai1/runs/<name>
    python tools/ai1/evaluate.py tools/ai1/runs/<name>

It re-checks every saved answer (output_<package>_run<k>.txt) with app.analysis.run_analysis,
writes each valid AnalysisReport to reports/<package>_run<k>.json, and writes evaluation.md and
evaluation.json with the per-run scores and metrics E1 to E11 (docs/ai1-report-schema.md).
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.analysis import ReportMeta, run_analysis  # noqa: E402
from app.analysis.metrics import ExpectedIncident, score_run, summarize  # noqa: E402
from app.contracts import EvidencePackage  # noqa: E402

AI1_FIXTURES = ROOT / "fixtures" / "ai1"
OUTPUT_NAME = re.compile(r"output_(?P<package>.+)_run(?P<run>\d+)\.txt")


def load_expected(path: Path) -> dict[str, ExpectedIncident]:
    items = [ExpectedIncident.model_validate(e) for e in json.loads(path.read_text("utf-8"))]
    return {Path(e.package).stem: e for e in items}


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def render_md(run_dir: Path, record: dict, scores, metrics) -> str:
    model = record.get("model", {})
    lines = [
        f"# AI1 evaluation: {run_dir.name}",
        "",
        f"- Model: {model.get('name', 'n/a')} | backend: {model.get('backend', 'n/a')}"
        f" | prompt: {model.get('prompt_version', 'n/a')}",
        f"- Runs scored: {len(scores)} | expectations: fixtures/ai1/expected.json",
        "",
        "| Metric | Name | Value | Target | Met |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {m.key} | {m.name} | {_fmt(m.value)} | {m.target} | {_fmt(m.passed)} |" for m in metrics
    ]
    lines += [
        "",
        "| Package | Run | Valid | Failed checks | Outcome | Attack type | Coverage | Grounding"
        " | Confidence | Freeze (as expected) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        freeze = f"{_fmt(s.would_freeze)} ({_fmt(s.freeze_match)})"
        lines.append(
            f"| {s.package} | {s.run} | {_fmt(s.valid)} | {', '.join(s.failed_checks) or '-'}"
            f" | {_fmt(s.outcome)} | {_fmt(s.attack_type)} | {_fmt(s.coverage)}"
            f" | {_fmt(s.grounding_rate)} | {_fmt(s.confidence)} | {freeze} |"
        )
    lines += [
        "",
        "Automatic metrics check structure and support, not truth. Score the key facts in"
        " fixtures/ai1/expected.json by hand for each valid report (docs/ai1-report-schema.md,"
        " section 6).",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("run_dir", type=Path, help="a bench.py --out folder")
    ap.add_argument("--packages", type=Path, default=AI1_FIXTURES / "packages")
    ap.add_argument("--expected", type=Path, default=AI1_FIXTURES / "expected.json")
    ap.add_argument("--site", choices=("hpc", "local"), default="local", help="where it ran")
    args = ap.parse_args(argv)

    expected = load_expected(args.expected)
    record_path = args.run_dir / "model_run_record.json"
    record = json.loads(record_path.read_text("utf-8")) if record_path.exists() else {}
    model = record.get("model", {})
    reports_dir = args.run_dir / "reports"
    reports_dir.mkdir(exist_ok=True)

    scores = []
    for path in sorted(args.run_dir.glob("output_*_run*.txt")):
        match = OUTPUT_NAME.fullmatch(path.name)
        if not match or match["package"] not in expected:
            continue
        name, run = match["package"], int(match["run"])
        package_file = args.packages / f"{name}.json"
        evidence = EvidencePackage.model_validate_json(package_file.read_text("utf-8"))
        meta = ReportMeta(
            report_id=f"rep-{name}-{run}"[:128],
            generated_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
            generated_by="mock" if model.get("backend") in (None, "stub") else args.site,
            model_id=model.get("name"),
        )
        result = run_analysis(path.read_text("utf-8"), evidence, meta)
        scores.append(score_run(name, run, result, evidence, expected[name]))
        if result.report:
            out = reports_dir / f"{name}_run{run}.json"
            with out.open("w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(result.report.model_dump(mode="json"), indent=2) + "\n")

    if not scores:
        print(f"no output_<package>_run<k>.txt files for the AI1 packages in {args.run_dir}")
        return 1
    metrics = summarize(scores)
    data = {
        "run_dir": args.run_dir.name,
        "model": model,
        "metrics": [m.__dict__ for m in metrics],
        "runs": [s.as_dict() for s in scores],
    }
    (args.run_dir / "evaluation.json").write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    text = render_md(args.run_dir, record, scores, metrics)
    (args.run_dir / "evaluation.md").write_text(text, "utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
