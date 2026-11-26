"""Platt scaling of the LLM's group opinion, and its report (risk-v1 step 5, design 9A.2 step 3).

    python -m app.confidence.llm_calibrate \\
        --calibration groups-calibration.jsonl opinions-calibration.jsonl \\
        --test groups-test.jsonl opinions-test.jsonl --out <run dir>

1. Join each groups file with its opinions file by group ID and evidence hash (an opinion of
   other evidence, or with an error, is counted and left out).
2. Fit Platt scaling on the calibration groups: p_llm = 1 / (1 + exp(-(a + b * logit(raw)))),
   a logistic regression with one input (Platt 1999).
3. The groups sample holds about as many benign as attack groups (app.confidence.groups); the
   real share of attack groups is lower. `prior_shift` = logit(natural share) - logit(sample
   share) is stored, and `predict(raw, prior="natural")` adds it to `a` (prior correction,
   Saerens et al. 2002). The step 6 stacker refits its own intercept on events either way.
4. Report on the test groups, per dataset and pooled: AUC, Brier score, ECE and reliability
   bins of the raw value and of p_llm (sample prior, so it matches the test sample), the mean
   p_llm per true class, and the error count.

Output in --out: llm_calibrator.json (a, b, prior_shift and the prompt, model and mode it holds
for; plain JSON, no code runs when it is loaded) and llm_report.json (counts and measures only).
"""

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.confidence.metrics import summary

CALIBRATOR_FORMAT = "icd-llm-calibrator-v1"
EPS = 1e-4
SETTINGS = ("prompt_version", "model_id", "mode", "samples", "temperature")


def logit(p: np.ndarray | float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=np.float64), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]


def join(groups_path: Path, opinions_path: Path) -> tuple[list[dict[str, Any]], Counter]:
    """Rows with y, raw, dataset and class; the newest valid opinion per group wins."""
    opinions: dict[str, dict[str, Any]] = {}
    for line in _read_jsonl(opinions_path):
        opinions[line["group_id"]] = line  # later lines replace earlier ones (re-runs)
    rows, skipped = [], Counter()
    settings: set[tuple] = set()
    for group in _read_jsonl(groups_path):
        line = opinions.get(group["group_id"])
        if line is None:
            skipped["no_opinion"] += 1
        elif line["evidence_sha256"] != group["evidence_sha256"]:
            skipped["other_evidence"] += 1
        elif line.get("error") is not None or line.get("raw") is None:
            skipped["opinion_error"] += 1
        elif group.get("y") is None:
            skipped["no_label"] += 1
        else:
            used = tuple(line[k] for k in SETTINGS)
            settings.add(used)
            rows.append({"y": int(group["y"]), "raw": float(line["raw"]),
                         "dataset": group["dataset_id"], "cls": group.get("true_class"),
                         "settings": used})  # fmt: skip
    if len(settings) > 1:
        raise SystemExit(f"error: {opinions_path} mixes prompts, models or modes: {settings}")
    return rows, skipped


class PlattCalibrator:
    def __init__(self, a: float, b: float, prior_shift: float = 0.0,
                 meta: dict[str, Any] | None = None) -> None:  # fmt: skip
        self.a, self.b, self.prior_shift = a, b, prior_shift
        self.meta = meta or {}

    def predict(self, raw: np.ndarray | float, prior: str = "natural") -> np.ndarray:
        a = self.a + (self.prior_shift if prior == "natural" else 0.0)
        return 1.0 / (1.0 + np.exp(-(a + self.b * logit(raw))))

    def to_json(self) -> dict[str, Any]:
        return {"format": CALIBRATOR_FORMAT, "a": self.a, "b": self.b,
                "prior_shift": self.prior_shift, **self.meta}  # fmt: skip


def fit_platt(raw: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    from sklearn.linear_model import LogisticRegression

    y = np.asarray(y, dtype=np.int8)
    if len(np.unique(y)) < 2:
        raise SystemExit("error: the calibration groups need both attack and benign groups")
    model = LogisticRegression(C=1e6, max_iter=1000)
    model.fit(logit(raw).reshape(-1, 1), y)
    return float(model.intercept_[0]), float(model.coef_[0][0])


def prior_shift(natural_share: float | None, sample_share: float) -> float:
    if natural_share is None or not 0 < natural_share < 1 or not 0 < sample_share < 1:
        return 0.0
    return float(logit(natural_share) - logit(sample_share))


def _natural_share(groups_path: Path) -> float | None:
    manifest = groups_path.with_suffix(".manifest.json")
    if not manifest.is_file():
        return None
    info = json.loads(manifest.read_text(encoding="utf-8"))["datasets"].values()
    total = sum(d["groups_in_split"] for d in info)
    return sum(d["attack_groups_in_split"] for d in info) / total if total else None


def report(cal: PlattCalibrator, rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in sorted({r["dataset"] for r in rows}) + ["pooled"]:
        part = [r for r in rows if name in ("pooled", r["dataset"])]
        y = np.array([r["y"] for r in part])
        raw = np.array([r["raw"] for r in part])
        p = cal.predict(raw, prior="sample")
        classes = sorted({r["cls"] for r in part if r["cls"] is not None})
        out[name] = {
            "raw": summary(y, raw),
            "calibrated": summary(y, p),
            "mean_p_llm_by_class": {
                c: float(np.mean([pi for pi, r in zip(p, part, strict=True) if r["cls"] == c]))
                for c in classes
            },
        }
    return out


def run(calibration: tuple[Path, Path], test: tuple[Path, Path] | None, out: Path) -> dict:
    cal_rows, cal_skipped = join(*calibration)
    if not cal_rows:
        raise SystemExit("error: no calibration group has a valid opinion")
    y = np.array([r["y"] for r in cal_rows])
    raw = np.array([r["raw"] for r in cal_rows])
    a, b = fit_platt(raw, y)
    natural = _natural_share(calibration[0])
    shift = prior_shift(natural, float(y.mean()))
    prompt_version, model_id, mode, samples, temperature = cal_rows[0]["settings"]
    created = datetime.now(UTC).isoformat(timespec="seconds")
    calibrator = PlattCalibrator(a, b, shift, {
        "prompt_version": prompt_version, "model_id": model_id, "mode": mode,
        "samples": samples, "temperature": temperature, "created": created,
        "calibration_groups": len(cal_rows), "calibration_attack_share": float(y.mean()),
        "natural_attack_share": natural,
    })  # fmt: skip
    result: dict[str, Any] = {
        "format": "icd-llm-report-v1",
        "created": created,
        "calibrator": calibrator.to_json(),
        "skipped": {"calibration": dict(cal_skipped)},
        "calibration": report(calibrator, cal_rows),
    }
    if test is not None:
        test_rows, test_skipped = join(*test)
        if test_rows and test_rows[0]["settings"] != cal_rows[0]["settings"]:
            raise SystemExit("error: the test opinions used another prompt, model or mode")
        result["skipped"]["test"] = dict(test_skipped)
        result["test"] = report(calibrator, test_rows) if test_rows else {}
    out.mkdir(parents=True, exist_ok=True)
    (out / "llm_calibrator.json").write_text(
        json.dumps(calibrator.to_json(), indent=2) + "\n", encoding="utf-8"
    )
    (out / "llm_report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def load(path: Path, prompt_version: str | None = None, model_id: str | None = None,
         mode: str | None = None) -> PlattCalibrator:  # fmt: skip
    """A calibrator written by run(); refuses another format, prompt, model or mode."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != CALIBRATOR_FORMAT:
        raise ValueError(f"{path} is not an {CALIBRATOR_FORMAT} file")
    for key, wanted in (("prompt_version", prompt_version), ("model_id", model_id),
                        ("mode", mode)):  # fmt: skip
        if wanted is not None and data.get(key) != wanted:
            raise ValueError(f"{path} was fitted for {key} {data.get(key)!r}, not {wanted!r}")
    meta = {k: v for k, v in data.items() if k not in ("format", "a", "b", "prior_shift")}
    return PlattCalibrator(float(data["a"]), float(data["b"]), float(data["prior_shift"]), meta)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--calibration", nargs=2, type=Path, required=True,
                        metavar=("GROUPS", "OPINIONS"))  # fmt: skip
    parser.add_argument("--test", nargs=2, type=Path, metavar=("GROUPS", "OPINIONS"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run(tuple(args.calibration), tuple(args.test) if args.test else None, args.out)
    cal = result["calibrator"]
    print(f"Platt a={cal['a']:.4f} b={cal['b']:.4f} prior_shift={cal['prior_shift']:.4f}")
    for name, entry in result.get("test", {}).items():
        m = entry["calibrated"]
        auc = "n/a" if m["auc"] is None else f"{m['auc']:.4f}"
        print(f"test {name}: groups {m['rows']}, AUC {auc}, ECE {m['ece']:.4f}, "
              f"Brier {m['brier']:.4f}")  # fmt: skip
    return 0 if math.isfinite(cal["a"]) else 1


if __name__ == "__main__":
    sys.exit(main())
