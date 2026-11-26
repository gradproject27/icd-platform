"""Fit and check the confidence stacker on real groups (risk-v1 step 6a).

    python -m app.confidence.stack_fit --out <run dir> \\
        --model <step 4 run>/model.joblib --llm-calibrator <step 5 run>/llm_calibrator.json \\
        --calibration groups-calibration.jsonl opinions-calibration.jsonl \\
        --test groups-test.jsonl opinions-test.jsonl \\
        --input nf-unsw-nb15-v3=<path> --input nf-cse-cic-ids2018-v3=<path>

The step 5 groups hold a masked description, not the 47 features, so the CSVs are read again
and the flows of each chosen group (the same 50 earliest flows) get their calibrated p_clf from
the step 4 model. Every event of a group carries the group's p_llm (Platt, natural prior) and
the group's label. app.confidence.stack then fits the stacker on one half of the calibration
groups and the conformal threshold on the other; the test groups give the report.

Output: stacker.json (weights, threshold, the versions of the classifier and the LLM
calibrator it was fitted with) and stack_report.json (counts and measures only).
"""

import argparse
import hashlib
import heapq
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from app.confidence import features as F
from app.confidence import llm_calibrate as LC
from app.confidence import stack as S
from app.confidence.groups import MAX_FLOWS, _key, _number
from app.ingest.nf_v3 import COLUMNS


def _groups(groups_path: Path, opinions_path: Path) -> dict[str, dict[str, Any]]:
    """group_id -> {y, raw, dataset} for groups with a valid opinion."""
    opinions = {o["group_id"]: o for o in LC._read_jsonl(opinions_path)}
    out = {}
    for g in LC._read_jsonl(groups_path):
        o = opinions.get(g["group_id"])
        if (
            o
            and o.get("error") is None
            and o.get("raw") is not None
            and o["evidence_sha256"] == g["evidence_sha256"]
            and g.get("y") is not None
        ):
            out[g["group_id"]] = {"y": int(g["y"]), "raw": float(o["raw"]),
                                  "dataset": g["dataset_id"], "split": g["split"]}  # fmt: skip
    return out


def _features(dataset_id: str, path: Path, split: str, wanted: set[str],
              block_minutes: int = F.BLOCK_MINUTES) -> dict[str, np.ndarray]:  # fmt: skip
    """group_id -> feature rows of its 50 earliest flows (as app.confidence.groups keeps)."""
    import pyarrow as pa
    from pyarrow import csv

    reader = csv.open_csv(
        path,
        read_options=csv.ReadOptions(block_size=64 << 20),
        convert_options=csv.ConvertOptions(column_types={n: pa.string() for n in COLUMNS}),
    )
    heaps: dict[str, list] = {}
    splits: dict[int, str] = {}
    serial = 0
    for batch in reader:
        cols = {n: batch.column(n).to_pylist() for n in COLUMNS}
        for i in range(batch.num_rows):
            key = _key(dataset_id, cols, i, block_minutes, splits)
            if key is None or key[0] != split:
                continue
            _, block, cls, source = key
            digest = hashlib.sha256(f"{dataset_id}|{block}|{cls}|{source}".encode()).hexdigest()
            group_id = f"{dataset_id}:{split}:{digest[:16]}"
            if group_id not in wanted:
                continue
            row = [_number(cols[n][i]) for n in F.FEATURES]
            x = np.array([np.nan if v is None else v for v in row], dtype=np.float32)
            serial += 1
            item = (-int(float(cols["FLOW_START_MILLISECONDS"][i])), -serial, x)
            heap = heaps.setdefault(group_id, [])
            if len(heap) < MAX_FLOWS:
                heapq.heappush(heap, item)
            elif item[:2] > heap[0][:2]:
                heapq.heapreplace(heap, item)
    return {g: np.stack([item[2] for item in heap]) for g, heap in heaps.items()}


def events(groups: dict[str, dict[str, Any]], inputs: dict[str, Path], split: str,
           model, llm: LC.PlattCalibrator) -> dict[str, Any]:  # fmt: skip
    p_clf, p_llm, y, ids, datasets = [], [], [], [], []
    for dataset_id, path in sorted(inputs.items()):
        wanted = {g for g, info in groups.items() if info["dataset"] == dataset_id}
        if not wanted:
            continue
        for group_id, X in sorted(_features(dataset_id, path, split, wanted).items()):
            info = groups[group_id]
            p_clf.append(model.predict(X))
            p_llm.append(np.full(len(X), float(llm.predict(info["raw"], prior="natural"))))
            y.append(np.full(len(X), info["y"], dtype=np.int8))
            ids += [group_id] * len(X)
            datasets += [dataset_id] * len(X)
    if not ids:
        raise SystemExit(f"error: no {split} group was found in the CSVs")
    return {"p_clf": np.concatenate(p_clf), "p_llm": np.concatenate(p_llm),
            "y": np.concatenate(y), "ids": ids, "datasets": np.array(datasets)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    from app.confidence.train import load as load_model

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--llm-calibrator", type=Path, required=True)
    parser.add_argument("--calibration", nargs=2, type=Path, required=True)
    parser.add_argument("--test", nargs=2, type=Path, required=True)
    parser.add_argument("--input", action="append", required=True, metavar="DATASET_ID=PATH")
    parser.add_argument("--alpha", type=float, default=S.ALPHA)
    args = parser.parse_args(argv)
    inputs = {k.strip(): Path(v) for k, v in (i.partition("=")[::2] for i in args.input)}
    model = load_model(args.model)
    llm = LC.load(args.llm_calibrator)
    cal = events(_groups(*args.calibration), inputs, "calibration", model, llm)
    natural = LC._natural_share(args.calibration[0])
    meta = {"classifier": args.model.name, "llm_calibrator": llm.meta}
    stacker, counts = S.fit(cal["p_clf"], cal["p_llm"], cal["y"], cal["ids"], natural,
                            args.alpha, meta)  # fmt: skip
    test = events(_groups(*args.test), inputs, "test", model, llm)
    report: dict[str, Any] = {"format": "icd-stack-report-v1", "stacker": stacker.to_json(),
                              "counts": counts, "test": {}}  # fmt: skip
    for name in sorted(set(test["datasets"])) + ["pooled"]:
        mask = np.ones(len(test["y"]), bool) if name == "pooled" else test["datasets"] == name
        report["test"][name] = S.evaluate(stacker, test["p_clf"][mask], test["p_llm"][mask],
                                          test["y"][mask])  # fmt: skip
    S.save(stacker, args.out / "stacker.json")
    (args.out / "stack_report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                encoding="utf-8")  # fmt: skip
    pooled = report["test"]["pooled"]
    print(f"stacker b_clf={stacker.b_clf:.3f} b_llm={stacker.b_llm:.3f} q={stacker.threshold:.3f};"
          f" test coverage {pooled['conformal_coverage']:.3f}, review share "
          f"{pooled['needs_review_share']:.3f}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
