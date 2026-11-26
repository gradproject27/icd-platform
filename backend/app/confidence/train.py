"""Fit, calibrate and evaluate the confidence classifier (risk-v1 step 4, design 9A.2 steps 1-2).

    python -m app.confidence.train --prepared <dir> --out <run dir>
    python -m app.confidence.train --prepared <dir> --out <run dir> --train-datasets nf-unsw-nb15-v3
    python -m app.confidence.train --prepared <dir> --out <run dir> --model lightgbm

1. Fit gradient-boosted trees on the train split: scikit-learn's HistGradientBoostingClassifier
   by default (no extra package), or LightGBM with --model lightgbm when it is installed.
   --train-datasets limits training and calibration to some datasets; the test report still
   covers every dataset, which gives the cross-dataset results of design 9A.2.
2. Fit isotonic regression on the calibration split (never seen in training), so a calibrated
   value of 0.8 means "an attack about 8 times in 10".
3. Report on the test split, per dataset and as a macro average: AUC, Brier score, expected
   calibration error (ECE) and reliability bins, before and after calibration; the pass marks
   of design 9A.2 (ECE <= 0.05, AUC >= 0.95) are checked in-dataset only.

Output in --out: model.joblib (the model, the calibrator, the feature list and every version
behind them) and report.json (counts and measures only, no row). A joblib file runs code when
loaded: load only files the team made.
"""

import argparse
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.confidence import features as F
from app.confidence.metrics import summary

BUNDLE_FORMAT = "icd-confidence-model-v1"
PASS_ECE = 0.05
PASS_AUC = 0.95
SEED = 20261126


def load_split(prepared: Path, split: str) -> dict[str, np.ndarray]:
    with np.load(prepared / f"{split}.npz") as data:
        return {key: data[key] for key in ("X", "y", "dataset", "cls")}


def _select(part: dict[str, np.ndarray], codes: set[int]) -> dict[str, np.ndarray]:
    mask = np.isin(part["dataset"], list(codes))
    return {key: value[mask] for key, value in part.items()}


def make_model(kind: str, threads: int | None = None):
    if kind == "hgb":
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.1, max_leaf_nodes=63, l2_regularization=1.0,
            early_stopping=True, validation_fraction=0.1, n_iter_no_change=20,
            random_state=SEED,
        )  # fmt: skip
    if kind == "lightgbm":
        try:
            from lightgbm import LGBMClassifier
        except ImportError as exc:
            raise SystemExit("error: --model lightgbm needs `pip install lightgbm`") from exc
        return LGBMClassifier(
            n_estimators=600, learning_rate=0.05, num_leaves=63, reg_lambda=1.0,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=SEED,
            n_jobs=threads or -1, verbose=-1,
        )  # fmt: skip
    raise SystemExit(f"error: unknown model {kind}")


class CalibratedConfidence:
    """The fitted model and its isotonic calibrator; predict() gives calibrated p_clf."""

    def __init__(self, model: Any, calibrator: Any, features: tuple[str, ...]) -> None:
        self.model = model
        self.calibrator = calibrator
        self.features = features

    def raw(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(X)[:, 1]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.clip(self.calibrator.predict(self.raw(X)), 0.0, 1.0)


def fit(train: dict[str, np.ndarray], calibration: dict[str, np.ndarray], kind: str,
        threads: int | None = None) -> CalibratedConfidence:  # fmt: skip
    from sklearn.isotonic import IsotonicRegression

    if len(np.unique(train["y"])) < 2:
        raise SystemExit("error: the train split needs both attack and benign rows")
    model = make_model(kind, threads)
    model.fit(train["X"], train["y"])
    calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    raw = model.predict_proba(calibration["X"])[:, 1]
    calibrator.fit(raw, calibration["y"])
    return CalibratedConfidence(model, calibrator, F.FEATURES)


def evaluate(model: CalibratedConfidence, test: dict[str, np.ndarray], names: dict[int, str],
             trained_on: set[int], classes: list[str]) -> dict[str, Any]:  # fmt: skip
    report: dict[str, Any] = {"per_dataset": {}}
    in_dataset = []
    for code, name in sorted(names.items()):
        part = _select(test, {code})
        if not len(part["y"]):
            continue
        raw, calibrated = model.raw(part["X"]), model.predict(part["X"])
        entry = {
            "role": "in-dataset" if code in trained_on else "cross-dataset",
            "raw": summary(part["y"], raw),
            "calibrated": summary(part["y"], calibrated),
            "mean_confidence_by_class": {
                classes[c]: float(calibrated[part["cls"] == c].mean())
                for c in np.unique(part["cls"])
            },
        }
        if code in trained_on:
            cal = entry["calibrated"]
            entry["pass"] = {
                "ece": cal["ece"] <= PASS_ECE,
                "auc": cal["auc"] is not None and cal["auc"] >= PASS_AUC,
            }
            in_dataset.append(cal)
        report["per_dataset"][name] = entry
    if in_dataset:
        report["macro_in_dataset"] = {
            key: float(np.mean([m[key] for m in in_dataset if m[key] is not None]))
            for key in ("auc", "brier", "ece")
        }
    return report


def run(prepared: Path, out: Path, kind: str = "hgb", train_datasets: list[str] | None = None,
        threads: int | None = None) -> dict[str, Any]:  # fmt: skip
    import joblib
    import sklearn

    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    names = {info["code"]: name for name, info in manifest["datasets"].items()}
    wanted = set(train_datasets or names.values())
    unknown = wanted - set(names.values())
    if unknown:
        raise SystemExit(f"error: not in the prepared data: {', '.join(sorted(unknown))}")
    codes = {code for code, name in names.items() if name in wanted}

    train = _select(load_split(prepared, "train"), codes)
    calibration = _select(load_split(prepared, "calibration"), codes)
    test = load_split(prepared, "test")

    started = time.monotonic()
    model = fit(train, calibration, kind, threads)
    seconds = time.monotonic() - started
    report = {
        "format": "icd-confidence-report-v1",
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": kind,
        "feature_set": manifest["feature_set"],
        "trained_on": sorted(wanted),
        "rows": {
            "train": int(len(train["y"])),
            "calibration": int(len(calibration["y"])),
            "test": int(len(test["y"])),
        },  # fmt: skip
        "fit_seconds": round(seconds, 1),
        "pass_marks": {"ece_max": PASS_ECE, "auc_min": PASS_AUC},
        **evaluate(model, test, names, codes, manifest["classes"]),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "prepared": manifest["created"],
            "inputs": {n: i["sha256"] for n, i in manifest["datasets"].items()},
        },
    }
    if kind == "lightgbm":
        import lightgbm

        report["versions"]["lightgbm"] = lightgbm.__version__
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "format": BUNDLE_FORMAT,
            "feature_set": F.FEATURE_SET_VERSION,
            "features": list(F.FEATURES),
            "model": model.model,
            "calibrator": model.calibrator,
            "versions": report["versions"],
            "trained_on": report["trained_on"],
            "created": report["created"],
        },
        out / "model.joblib",
    )
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def load(path: Path) -> CalibratedConfidence:
    """A bundle written by run(); refuses another format or feature set."""
    import joblib

    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT:
        raise ValueError(f"{path} is not an {BUNDLE_FORMAT} file")
    if tuple(bundle["features"]) != F.FEATURES:
        raise ValueError(f"{path} was trained on other features ({bundle['feature_set']})")
    return CalibratedConfidence(bundle["model"], bundle["calibrator"], F.FEATURES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", choices=("hgb", "lightgbm"), default="hgb")
    parser.add_argument("--train-datasets", nargs="+", choices=F.DATASETS)
    parser.add_argument("--threads", type=int)
    args = parser.parse_args(argv)
    report = run(args.prepared, args.out, args.model, args.train_datasets, args.threads)
    for name, entry in report["per_dataset"].items():
        cal = entry["calibrated"]
        auc = "n/a" if cal["auc"] is None else f"{cal['auc']:.4f}"
        print(f"{name} ({entry['role']}): AUC {auc}, ECE {cal['ece']:.4f}, "
              f"Brier {cal['brier']:.4f}, pass {entry.get('pass', '-')}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
