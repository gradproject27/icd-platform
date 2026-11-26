"""The cluster side of the confidence handoff (risk-v1 step 6b): one input file in, one output out.

    python -m app.confidence.batch_run --input <in.json> --output <out.json> \\
        --model model.joblib --llm-calibrator llm_calibrator.json --stacker stacker.json \\
        --endpoint http://127.0.0.1:8000/v1/chat/completions --llm-model <served name>

1. p_clf for every event: the step 4 model and its isotonic calibrator (train.load).
2. p_llm for every group: the step 5 prompt (llm_opinion), then Platt scaling with the natural
   prior (llm_calibrate). A group whose opinion fails keeps no p_llm.
3. C per event (stack.combine): stacked with conformal needs_review when p_llm exists, else
   calibrated p_clf with llm_unavailable.

Paths and the model server also come from ICD_CONFIDENCE_MODEL, ICD_CONFIDENCE_LLM_CALIBRATOR,
ICD_CONFIDENCE_STACKER, ICD_LLM_ENDPOINT and ICD_LLM_MODEL (tools/confidence/icd_confidence.sbatch).
Any failure of the whole run is written as an output with `error`, never as made-up values.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.confidence.handoff import INPUT_FORMAT, ConfidenceOutput, EventValue


def _short(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def run(data: dict[str, Any], model_path: Path, calibrator_path: Path, stacker_path: Path,
        client) -> ConfidenceOutput:  # fmt: skip
    import numpy as np

    from app.confidence import features as F
    from app.confidence import llm_calibrate as LC
    from app.confidence import stack as S
    from app.confidence.llm_opinion import opinion
    from app.confidence.train import load as load_model

    if data.get("format") != INPUT_FORMAT or tuple(data.get("features", ())) != F.FEATURES:
        raise ValueError("not an icd-confidence-input-v1 file for this feature set")
    model = load_model(model_path)
    llm = LC.load(calibrator_path, prompt_version=None, model_id=client.model_id, mode=client.mode)
    stacker = S.load(stacker_path)

    events = data["events"]
    X = np.array(
        [[np.nan if v is None else v for v in e["features"]] for e in events], dtype=np.float32
    ).reshape(len(events), len(F.FEATURES))
    p_clf = dict(zip([e["event_id"] for e in events], map(float, model.predict(X)), strict=True))

    p_llm: dict[str, float | None] = {}
    for group in data["groups"]:
        line = opinion(client, group)
        value = None if line["raw"] is None else float(llm.predict(line["raw"], prior="natural"))
        for event_id in group["event_ids"]:
            p_llm[event_id] = value

    values = {}
    for event_id, p in p_clf.items():
        conf = S.combine(p, p_llm.get(event_id), stacker, llm_flag="llm_unavailable")
        values[event_id] = EventValue(c=conf.c, p_clf=p, p_llm=conf.p_llm, flags=list(conf.flags))
    versions = {
        "classifier": f"{model_path.name}@{_short(model_path)}",
        "llm_calibrator": f"{calibrator_path.name}@{_short(calibrator_path)}",
        "stacker": f"{stacker_path.name}@{_short(stacker_path)}",
        "llm_model": client.model_id,
        "prompt": str(llm.meta.get("prompt_version")),
        "feature_set": F.FEATURE_SET_VERSION,
    }
    short = [_short(p)[:8] for p in (model_path, calibrator_path, stacker_path)]
    version = "clf-{}+llm-{}+stack-{}".format(*short)
    return ConfidenceOutput(request_id=data["request_id"], version=version, versions=versions,
                            events=values)  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    from app.confidence.llm_opinion import OpinionClient, http_post

    env = os.environ
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", type=Path, default=env.get("ICD_CONFIDENCE_INPUT"))
    parser.add_argument("--output", type=Path, default=env.get("ICD_CONFIDENCE_OUTPUT"))
    parser.add_argument("--model", type=Path, default=env.get("ICD_CONFIDENCE_MODEL"))
    parser.add_argument("--llm-calibrator", type=Path,
                        default=env.get("ICD_CONFIDENCE_LLM_CALIBRATOR"))  # fmt: skip
    parser.add_argument("--stacker", type=Path, default=env.get("ICD_CONFIDENCE_STACKER"))
    parser.add_argument("--endpoint", default=env.get("ICD_LLM_ENDPOINT"))
    parser.add_argument("--llm-model", default=env.get("ICD_LLM_MODEL"))
    parser.add_argument("--revision", default=env.get("ICD_LLM_REVISION"))
    parser.add_argument("--mode", choices=("samples", "logprobs"), default="samples")
    parser.add_argument("--no-thinking", action="store_true")
    args = parser.parse_args(argv)
    for name in ("input", "output", "model", "llm_calibrator", "stacker", "endpoint",
                 "llm_model"):  # fmt: skip
        if not getattr(args, name):
            parser.error(f"--{name.replace('_', '-')} (or its ICD_* variable) is needed")
    request_id = "unknown"
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        request_id = str(data.get("request_id", request_id))
        client = OpinionClient(
            post=http_post(args.endpoint, env.get("ICD_LLM_API_KEY") or None, 120),
            model=args.llm_model,
            model_id=f"{args.llm_model}@{args.revision}" if args.revision else args.llm_model,
            mode=args.mode, no_thinking=args.no_thinking,
        )  # fmt: skip
        output = run(data, args.model, args.llm_calibrator, args.stacker, client)
    except Exception as exc:  # the worker must get an answer file, never silence
        output = ConfidenceOutput(request_id=request_id, error=f"{type(exc).__name__}: {exc}")
    args.output.write_text(output.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return 0 if output.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
