"""Run the AI analysis on evidence packages and validate its grounding (AI1, Week 3).

This is the runbook command (docs/ai1-runbook.md) and the step 10C grounding validation tool.
For each package: cache lookup, prompt v2, one schema retry, all checks, computed confidence.
It writes, under --out:
    grounding-validation.md / .json   per-incident claim counts and the totals
    reports/<name>.json               each valid report (masked, as stored)
    raw/<name>.try<n>.txt             each model answer, failed ones included
With --from-db the packages come from incidents stored in the database (DATABASE_URL), and only
the counts are written (--counts-only is forced): real dataset text never lands in the files.

Run from the repo root (backend venv active):
    python tools/ai1/run_analysis.py --packages fixtures/ai1/grounding-set \
        --out tools/ai1/runs/stub-20
    python tools/ai1/run_analysis.py --packages fixtures/ai1/grounding-set \
        --out tools/ai1/runs/cluster-v2 --backend openai_http \
        --endpoint http://127.0.0.1:<tunnel port>/v1/chat/completions \
        --model qwen3.8-27b-awq-int4 --site hpc --no-thinking
        (the cluster key is read from the ICD_LLM_API_KEY or OPENAI_API_KEY variable)
    python tools/ai1/run_analysis.py --from-db --upload <upload_id> --limit 20 \
        --out tools/ai1/runs/unsw-20 ...
    python tools/ai1/run_analysis.py --packages fixtures/ai1/packages \
        tools/ai1/samples/evidence-inc-ai1-0001.json --backend replay \
        --answers docs/ai1-runs/09-csit-qwen27b-awq-v1 --replay-run 1 --site hpc --out ...
        (re-checks answers recorded by bench.py, without a model: no retry, no cache)

Exit code: 0 every package was analysed (valid or not), 2 bad input or settings.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.analysis.backends import BackendError, Generation, OpenAIHttpGenerator  # noqa: E402
from app.analysis.cache import FileReportCache  # noqa: E402
from app.analysis.prompt import PROMPT_FILES, PROMPT_VERSION  # noqa: E402
from app.analysis.service import analyze_package  # noqa: E402
from app.analysis.stub import StubGenerator  # noqa: E402
from app.analysis.validation import grounding_row, render_markdown, summarize  # noqa: E402
from app.contracts import EvidencePackage  # noqa: E402

DEFAULT_CACHE = ROOT / "tools" / "ai1" / "runs" / "cache"


def clock() -> datetime:
    return datetime.now(UTC)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def package_files(items: list[Path]) -> list[Path]:
    """Files as given; a folder means every *.json in it, sorted by name."""
    files: list[Path] = []
    for item in items:
        files += sorted(item.glob("*.json")) if item.is_dir() else [item]
    return files


class ReplayGenerator:
    """Answers with a recorded bench.py answer: <answers>/output_<package name>_run<n>.txt."""

    def __init__(self, answers: Path, run: int, site: str) -> None:
        record = json.loads((answers / "model_run_record.json").read_text(encoding="utf-8"))
        self.model_id = record["model"]["name"]
        self.prompt_version = record["model"].get("prompt_version", "ai1-prompt-v0")
        self.generated_by = site  # bench.py records do not say where the model ran
        self.answers, self.run, self.name = answers, run, ""

    def generate(self, messages, evidence):
        path = self.answers / f"output_{self.name}_run{self.run}.txt"
        if not path.exists():
            raise BackendError(f"no recorded answer {path.name}")
        return Generation(path.read_text(encoding="utf-8"))


def generator(args):
    if args.backend == "stub":
        return StubGenerator()
    if args.backend == "replay":
        if not args.answers:
            raise ValueError("--backend replay needs --answers")
        return ReplayGenerator(args.answers, args.replay_run, args.site)
    key = os.environ.get("ICD_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    return OpenAIHttpGenerator(
        args.endpoint,
        args.model,
        site=args.site,
        revision=args.revision,
        api_key=key,
        timeout_seconds=args.timeout,
        max_tokens=args.max_new_tokens,
        temperature=args.temperature,
        no_thinking=args.no_thinking,
        json_schema=args.json_schema,
    )


def packages_from_db(args) -> list[tuple[str, EvidencePackage]]:
    """Masked packages of stored incidents, built with C2's builder (maps stored as usual)."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db import get_engine
    from app.evidence.store import build_and_store_for_incident
    from app.incidents.models import IncidentRow

    engine = get_engine()
    ids = list(args.incident or [])
    if args.upload:
        with Session(engine) as session:
            ids += session.scalars(
                select(IncidentRow.incident_id)
                .where(IncidentRow.upload_id == args.upload)
                .order_by(IncidentRow.first_event_at, IncidentRow.incident_id)
                .limit(args.limit)
            ).all()
    return [
        (f"db-{n:02d}", build_and_store_for_incident(engine, incident_id, clock()))
        for n, incident_id in enumerate(ids[: args.limit], start=1)
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--packages", type=Path, nargs="+", help="package files or folders")
    source.add_argument("--from-db", action="store_true", help="stored incidents (DATABASE_URL)")
    ap.add_argument("--incident", action="append", help="--from-db: an incident ID (repeatable)")
    ap.add_argument("--upload", help="--from-db: every incident of this upload, earliest first")
    ap.add_argument("--limit", type=int, default=20, help="--from-db: at most this many")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--backend", choices=("stub", "openai_http", "replay"), default="stub")
    ap.add_argument("--answers", type=Path, help="replay: a bench.py run folder")
    ap.add_argument("--replay-run", type=int, default=1, help="replay: which run's answers")
    ap.add_argument("--no-retry", action="store_true", help="turn the schema retry off")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434/v1/chat/completions")
    ap.add_argument("--model", default="qwen3-4b-instruct-10k")
    ap.add_argument("--revision", default=None, help="weights commit, if known")
    ap.add_argument("--site", choices=("hpc", "local"), default="local")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--max-new-tokens", type=int, default=4900)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--no-thinking", action="store_true")
    ap.add_argument("--json-schema", action="store_true")
    ap.add_argument("--prompt-version", choices=sorted(PROMPT_FILES), default=PROMPT_VERSION)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--no-cache", action="store_true", help="never read or write the cache")
    ap.add_argument("--force", action="store_true", help="re-analyse; store the new report")
    ap.add_argument("--counts-only", action="store_true", help="no reports or raw answers")
    args = ap.parse_args(argv)

    try:
        if args.from_db:
            if not (args.incident or args.upload):
                ap.error("--from-db needs --incident or --upload")
            args.counts_only = True
            named = packages_from_db(args)
        else:
            named = [
                (path.stem, EvidencePackage.model_validate_json(path.read_text(encoding="utf-8")))
                for path in package_files(args.packages)
            ]
        gen = generator(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not named:
        print("error: no packages", file=sys.stderr)
        return 2

    replay = isinstance(gen, ReplayGenerator)
    if replay:  # recorded answers: their own prompt, one try, nothing cached
        args.prompt_version, args.no_retry, args.no_cache = gen.prompt_version, True, True
    cache = None if args.no_cache else FileReportCache(args.cache_dir)
    rows = []
    for name, evidence in named:
        if replay:
            gen.name = name
        attempt = analyze_package(
            evidence, gen, clock=clock, cache=cache, force=args.force,
            prompt_version=args.prompt_version, max_tries=1 if args.no_retry else 2,
        )  # fmt: skip
        row = grounding_row(name, attempt, evidence)
        rows.append(row)
        state = "valid" if attempt.valid else "FAILED"
        extra = " (cache)" if attempt.cache_hit else f" ({len(attempt.tries)} tries)"
        print(f"{name}: {state}{extra} supported {row.supported} unsupported {row.unsupported}"
              f" checks {','.join(row.hard_checks) or '-'}")  # fmt: skip
        if args.counts_only:
            continue
        if attempt.result.report is not None:
            report = attempt.result.report.model_dump(mode="json")
            _write(args.out / "reports" / f"{name}.json", json.dumps(report, indent=2) + "\n")
        for t in attempt.tries:
            if t.raw_output is not None:
                _write(args.out / "raw" / f"{name}.try{t.number}.txt", t.raw_output)

    setup = {
        "date": clock().strftime("%Y-%m-%d %H:%M UTC"),
        "backend": args.backend,
        "model": gen.model_id,
        "site": gen.generated_by,
        "prompt_version": args.prompt_version,
        "packages": "stored incidents (counts only)" if args.from_db else
                    ", ".join(str(p) for p in args.packages),
        "cache": "off" if cache is None else ("forced re-analysis" if args.force else "on"),
        "schema_retry": "off" if args.no_retry else "on",
    }  # fmt: skip
    if replay:
        setup["answers"] = f"{args.answers} (run {args.replay_run})"
    if args.backend == "openai_http":
        setup.update({k: v for k, v in gen.settings().items() if k != "endpoint"})
    summary = summarize(rows)
    record = {"setup": setup, "summary": summary, "incidents": [r.record() for r in rows]}
    if args.counts_only:  # incident IDs of real data are not needed to read the counts
        for item in record["incidents"]:
            item["incident_id"] = None
    _write(args.out / "grounding-validation.json", json.dumps(record, indent=2) + "\n")
    _write(
        args.out / "grounding-validation.md",
        render_markdown("Grounding validation", rows, summary, setup),
    )
    print(
        f"{summary['valid']} of {summary['incidents']} valid; "
        f"{summary['supported_claims']} supported, {summary['unsupported_claims']} unsupported "
        f"factual claims; written to {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
