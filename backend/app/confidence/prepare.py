"""Turn NetFlow v3 CSVs into split, sampled arrays for the confidence classifier (step 4).

    python -m app.confidence.prepare --out <dir> \\
        --input nf-unsw-nb15-v3=<path>/NF-UNSW-NB15-v3.csv \\
        --input nf-cse-cic-ids2018-v3=<path>/NF-CSE-CIC-IDS2018-v3.csv

Two passes over each file, read in batches with pyarrow, so a 20M-row file never sits in
memory whole:

1. Count rows per (split, class); a split is decided by time block (features.py).
2. Keep rows at a per-(split, class) rate:
   - train: at most --train-cap rows per attack class and --benign-cap benign rows, so one
     class (UNSW Generic, CIC DDoS) cannot dominate (design 9A.4, cap per class);
   - calibration and test: one uniform rate per dataset so at most --eval-rows rows remain,
     which keeps the dataset's natural attack ratio (design 9A.4).
   The draws use a fixed seed per (dataset, batch), so the same inputs give the same arrays.

Output: <dir>/<split>.npz per split (X float32 [rows, 47], y int8, dataset and class codes)
and <dir>/manifest.json (inputs with size and SHA-256, counts before and after sampling,
rates, settings). Rows whose Label is not 0 or 1, or whose start time is missing, are skipped
and counted, never guessed. The arrays hold real dataset rows: never commit them.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.confidence import features as F
from app.ingest.nf_v3 import COLUMNS

BATCH_BYTES = 64 << 20
SEED = 20261126


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _check_header(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        header = tuple(name.strip() for name in file.readline().rstrip("\r\n").split(","))
    if header != COLUMNS:
        raise SystemExit(f"error: {path} does not start with the 55-column NetFlow v3 header")


def _batches(path: Path):
    """(start_ms, label, attack, X) numpy arrays per batch; a value that is not a number is NaN."""
    import pyarrow as pa
    from pyarrow import csv

    types = {name: pa.string() for name in COLUMNS}
    reader = csv.open_csv(
        path,
        read_options=csv.ReadOptions(block_size=BATCH_BYTES),
        convert_options=csv.ConvertOptions(column_types=types, include_columns=list(COLUMNS)),
    )
    for batch in reader:
        start = _to_float(batch.column("FLOW_START_MILLISECONDS"))
        label = batch.column("Label").to_numpy(zero_copy_only=False)
        attack = batch.column("Attack").to_numpy(zero_copy_only=False)
        columns = [
            _to_float(batch.column(name)).to_numpy(zero_copy_only=False) for name in F.FEATURES
        ]
        X = np.column_stack(columns).astype(np.float32) if columns else np.empty((0, 0))
        yield _to_float_np(start), label, attack, X


def _to_float(column):
    import pyarrow as pa
    import pyarrow.compute as pc

    try:  # fast path: every value is a number
        return pc.cast(column, pa.float64())
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError):  # slow path: NaN for the bad ones
        values = [_float_or_nan(v) for v in column.to_pylist()]
        return pa.array(values, type=pa.float64())


def _float_or_nan(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _to_float_np(array) -> np.ndarray:
    return np.asarray(array.to_numpy(zero_copy_only=False), dtype=np.float64)


def _rows(
    dataset_id: str, start: np.ndarray, label: np.ndarray, attack: np.ndarray, block_minutes: int
):
    """Per row: split name, class name, or None when the row is skipped (reason)."""
    out_split, out_class, skipped = [], [], Counter()
    split_cache: dict[int, str] = {}
    for moment, raw_label, raw_attack in zip(start, label, attack, strict=True):
        text = (raw_label or "").strip()
        if text not in ("0", "1"):
            skipped["label_not_0_or_1"] += 1
            out_split.append(None)
            out_class.append(None)
            continue
        if not np.isfinite(moment):
            skipped["no_start_time"] += 1
            out_split.append(None)
            out_class.append(None)
            continue
        block = F.block_of(int(moment), block_minutes)
        if block not in split_cache:
            split_cache[block] = F.split_of_block(dataset_id, block)
        out_split.append(split_cache[block])
        out_class.append(F.class_of(int(text), raw_attack))
    return out_split, out_class, skipped


def count(dataset_id: str, path: Path, block_minutes: int) -> tuple[Counter, Counter]:
    counts: Counter = Counter()
    skipped: Counter = Counter()
    for start, label, attack, _ in _batches(path):
        splits, classes, skip = _rows(dataset_id, start, label, attack, block_minutes)
        skipped.update(skip)
        counts.update((s, c) for s, c in zip(splits, classes, strict=True) if s is not None)
    return counts, skipped


def rates(counts: Counter, train_cap: int, benign_cap: int, eval_rows: int) -> dict:
    """Keep-probability per (split, class)."""
    out: dict[tuple[str, str], float] = {}
    for split in ("calibration", "test"):
        total = sum(n for (s, _), n in counts.items() if s == split)
        rate = min(1.0, eval_rows / total) if total else 1.0
        for s, c in counts:
            if s == split:
                out[(s, c)] = rate
    for (s, c), n in counts.items():
        if s == "train":
            cap = benign_cap if c == F.BENIGN else train_cap
            out[(s, c)] = min(1.0, cap / n) if n else 1.0
    return out


def prepare(inputs: dict[str, Path], out: Path, train_cap: int = 100_000,
            benign_cap: int = 500_000, eval_rows: int = 1_000_000,
            block_minutes: int = F.BLOCK_MINUTES) -> dict[str, Any]:  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    collected: dict[str, dict[str, list]] = {
        split: {"X": [], "y": [], "dataset": [], "cls": []} for split in F.SPLITS
    }
    classes: list[str] = []
    manifest: dict[str, Any] = {
        "format": "icd-confidence-prepared-v1",
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "feature_set": F.FEATURE_SET_VERSION,
        "features": list(F.FEATURES),
        "settings": {
            "train_cap": train_cap,
            "benign_cap": benign_cap,
            "eval_rows": eval_rows,
            "block_minutes": block_minutes,
            "seed": SEED,
        },  # fmt: skip
        "datasets": {},
    }
    for code, (dataset_id, path) in enumerate(sorted(inputs.items())):
        if dataset_id not in F.DATASETS:
            raise SystemExit(f"error: {dataset_id} is not one of {', '.join(F.DATASETS)}")
        _check_header(path)
        counts, skipped = count(dataset_id, path, block_minutes)
        keep = rates(counts, train_cap, benign_cap, eval_rows)
        kept: Counter = Counter()
        for number, (start, label, attack, X) in enumerate(_batches(path)):
            splits, row_classes, _ = _rows(dataset_id, start, label, attack, block_minutes)
            rng = np.random.default_rng([SEED, code, number])
            draw = rng.random(len(splits))
            chosen: dict[str, list[int]] = {split: [] for split in F.SPLITS}
            for i, (split, cls) in enumerate(zip(splits, row_classes, strict=True)):
                if split is None or draw[i] >= keep[(split, cls)]:
                    continue
                if cls not in classes:
                    classes.append(cls)
                chosen[split].append(i)
                kept[(split, cls)] += 1
            for split, rows in chosen.items():
                if not rows:
                    continue
                index = np.asarray(rows)
                bucket = collected[split]
                bucket["X"].append(X[index].copy())  # a copy, so the batch can be freed
                row_cls = [classes.index(row_classes[i]) for i in rows]
                is_attack = [row_classes[i] != F.BENIGN for i in rows]
                bucket["y"].append(np.asarray(is_attack, dtype=np.int8))
                bucket["dataset"].append(np.full(len(rows), code, dtype=np.int8))
                bucket["cls"].append(np.asarray(row_cls, dtype=np.int16))
        manifest["datasets"][dataset_id] = {
            "code": code,
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "skipped": dict(skipped),
            "counts": _nest(counts),
            "kept": _nest(kept),
        }
    manifest["classes"] = classes
    width = len(F.FEATURES)
    for split, bucket in collected.items():
        np.savez_compressed(
            out / f"{split}.npz",
            X=_stack(bucket["X"], (0, width), np.float32),
            y=_stack(bucket["y"], (0,), np.int8),
            dataset=_stack(bucket["dataset"], (0,), np.int8),
            cls=_stack(bucket["cls"], (0,), np.int16),
        )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _stack(parts: list[np.ndarray], empty: tuple[int, ...], dtype) -> np.ndarray:
    return np.concatenate(parts).astype(dtype) if parts else np.empty(empty, dtype)


def _nest(counter: Counter) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for (split, cls), n in sorted(counter.items()):
        out.setdefault(split, {})[cls] = n
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", action="append", required=True, metavar="DATASET_ID=PATH")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--train-cap", type=int, default=100_000)
    parser.add_argument("--benign-cap", type=int, default=500_000)
    parser.add_argument("--eval-rows", type=int, default=1_000_000)
    parser.add_argument("--block-minutes", type=int, default=F.BLOCK_MINUTES)
    args = parser.parse_args(argv)
    inputs = {}
    for item in args.input:
        dataset_id, _, path = item.partition("=")
        inputs[dataset_id.strip()] = Path(path)
        if not Path(path).is_file():
            print(f"error: {path} is not a file", file=sys.stderr)
            return 2
    manifest = prepare(inputs, args.out, args.train_cap, args.benign_cap, args.eval_rows,
                       args.block_minutes)  # fmt: skip
    for dataset_id, info in manifest["datasets"].items():
        kept = {split: sum(v.values()) for split, v in info["kept"].items()}
        print(f"{dataset_id}: kept {kept}, skipped {info['skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
