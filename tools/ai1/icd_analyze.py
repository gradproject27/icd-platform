"""The HPC analysis command (ICD_ANALYZE_CMD): one evidence file in, one icd-hpc-output-v1 out.

C1's sbatch script runs it on the cluster; it also runs on a laptop against a local model.
It sends prompt v0 with the evidence and writes the model's answer unchanged. It does not check
the answer: the app host does that with app.analysis.analyze_hpc_output.

    python tools/ai1/icd_analyze.py --evidence pkg.json --output out.json \
        --backend transformers --model /scratch/$USER/models/Qwen3-8B --revision <commit>
    python tools/ai1/icd_analyze.py --evidence pkg.json --output out.json --backend openai_http \
        --endpoint http://127.0.0.1:11434/v1/chat/completions --model qwen3:4b-instruct \
        --site local --json-schema

Exit code: 0 answer written, 1 the model failed (output file holds the error), 2 bad evidence.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from bench import BACKENDS  # noqa: E402

from app.analysis import PROMPT_VERSION, build_messages  # noqa: E402
from app.analysis.handoff import HPC_OUTPUT_FORMAT, HpcOutput, TokenUsage  # noqa: E402
from app.contracts import EvidencePackage  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--backend", choices=BACKENDS, default="transformers")
    ap.add_argument("--model", default="stub")
    ap.add_argument("--revision", default=None, help="weights commit hash")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8000/v1/chat/completions")
    ap.add_argument("--site", choices=("hpc", "local"), default="hpc")
    ap.add_argument("--load-4bit", action="store_true")
    ap.add_argument("--warmup", action="store_true")
    ap.add_argument("--json-schema", action="store_true")
    ap.add_argument("--max-new-tokens", type=int, default=3000)
    ap.add_argument("--temperature", type=float, default=0.0)
    args = ap.parse_args(argv)

    try:
        evidence = EvidencePackage.model_validate_json(args.evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"bad evidence file: {exc}", file=sys.stderr)
        return 2
    if not evidence.masked:
        print("refused: the evidence package is not masked (NFR-S-07)", file=sys.stderr)
        return 2

    backend = BACKENDS[args.backend](args)
    model_id = backend.model_name
    if args.revision:
        model_id = f"{model_id}@{args.revision}"
    started = datetime.now(UTC)
    raw, error, usage = None, None, {}
    try:
        backend.load()
        messages = build_messages(evidence)
        if args.backend == "stub":
            raw, usage = backend.generate(
                messages, args.max_new_tokens, args.temperature, args.evidence
            )
        else:
            raw, usage = backend.generate(messages, args.max_new_tokens, args.temperature)
    except Exception as exc:  # recorded in the output file, never lost
        error = f"{type(exc).__name__}: {exc}"
    output = HpcOutput(
        format=HPC_OUTPUT_FORMAT,
        package_id=evidence.package_id,
        incident_id=evidence.incident_id,
        generated_by=args.site,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        raw_output=raw,
        error=error,
        started_at=started,
        finished_at=datetime.now(UTC),
        usage=TokenUsage(**{k: v for k, v in usage.items() if k in TokenUsage.model_fields}),
        settings={
            "backend": args.backend,
            "temperature": args.temperature,
            "max_new_tokens": args.max_new_tokens,
            "json_schema": args.json_schema,
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(output.model_dump(mode="json"), indent=2) + "\n")
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
