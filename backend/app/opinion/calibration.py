"""Calibration of the LLM opinion (Platt scaling) and the measures to check it.

    p_llm = sigmoid(a * logit(clip(p_raw)) + b)

`a` and `b` are fitted on labelled groups (truth 1 attack, 0 normal) by Newton's method on the
log loss, with Platt's smoothed targets so a small set does not give 0 or 1 exactly. A
calibrator is tied to the method, prompt version and model it was fitted for; `estimate`
refuses to apply it to anything else.

Measures (design note 9A.2, pass marks proposed for step 7): Brier score, log loss, expected
calibration error (10 equal-width bins), AUC (Mann-Whitney, ties count half) and a reliability
table, per dataset and as a macro average (RV1-D5). `cross_validated` gives out-of-fold
calibrated values over contiguous time blocks (`time_blocks`), so the measures of the calibrated
opinion are never computed on the groups it was fitted on.

Pure Python: the backend has no numpy or scikit-learn, and two parameters do not need them.
"""

import math
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.opinion.models import OpinionMethod

CALIBRATOR_FORMAT = "icd-opinion-calibrator-v1"
EPS = 0.01  # p_raw is clipped to [EPS, 1 - EPS] before the logit (5 samples give 0 and 1)
BINS = 10


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    z = math.exp(x)
    return z / (1 + z)


def logit(p: float, eps: float = EPS) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


class Calibrator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["icd-opinion-calibrator-v1"] = CALIBRATOR_FORMAT
    version: str = Field(min_length=1, description="Name written into each GroupOpinion.")
    method: OpinionMethod
    prompt_version: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    a: float
    b: float
    eps: float = Field(default=EPS, gt=0, lt=0.5)
    fitted_on: int = Field(ge=2, description="Groups used for the fit.")
    positives: int = Field(ge=1)
    source: str = Field(min_length=1, description="Which labelled set, for the record.")
    fitted_at: datetime

    def apply(self, p_raw: float) -> float:
        return sigmoid(self.a * logit(p_raw, self.eps) + self.b)

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Calibrator":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def fit_platt(
    p_raw: Sequence[float], truth: Sequence[int], eps: float = EPS, iterations: int = 100
) -> tuple[float, float]:
    """(a, b) minimising the log loss of sigmoid(a * logit(p) + b) against Platt's targets."""
    if len(p_raw) != len(truth):
        raise ValueError("p_raw and truth must have the same length")
    positives = sum(1 for y in truth if y == 1)
    negatives = sum(1 for y in truth if y == 0)
    if positives + negatives != len(truth):
        raise ValueError("truth must be 0 or 1")
    if positives == 0 or negatives == 0:
        raise ValueError("calibration needs at least one attack group and one normal group")
    hi, lo = (positives + 1) / (positives + 2), 1 / (negatives + 2)
    xs = [logit(p, eps) for p in p_raw]
    ts = [hi if y == 1 else lo for y in truth]

    def loss(a: float, b: float) -> float:
        total = 0.0
        for x, t in zip(xs, ts, strict=True):
            z = a * x + b
            # log(1 + e^z) - t*z, written to stay finite for large |z|
            total += max(z, 0) + math.log1p(math.exp(-abs(z))) - t * z
        return total

    a, b = 1.0, 0.0
    current = loss(a, b)
    ridge = 1e-6  # keeps the Hessian invertible when every x is the same
    for _ in range(iterations):
        g_a = g_b = h_aa = h_ab = h_bb = 0.0
        for x, t in zip(xs, ts, strict=True):
            p = sigmoid(a * x + b)
            d, w = p - t, p * (1 - p)
            g_a += d * x
            g_b += d
            h_aa += w * x * x
            h_ab += w * x
            h_bb += w
        h_aa += ridge
        h_bb += ridge
        det = h_aa * h_bb - h_ab * h_ab
        if det <= 0:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / det
        step_b = (h_aa * g_b - h_ab * g_a) / det
        scale = 1.0
        while scale > 1e-8:  # halve the step until the loss does not go up
            trial = loss(a - scale * step_a, b - scale * step_b)
            if trial <= current + 1e-12:
                break
            scale /= 2
        else:
            break
        a, b, current = a - scale * step_a, b - scale * step_b, trial
        if abs(scale * step_a) < 1e-10 and abs(scale * step_b) < 1e-10:
            break
    return a, b


def brier(p: Sequence[float], truth: Sequence[int]) -> float:
    return sum((pi - yi) ** 2 for pi, yi in zip(p, truth, strict=True)) / len(p)


def log_loss(p: Sequence[float], truth: Sequence[int], eps: float = 1e-6) -> float:
    total = 0.0
    for pi, yi in zip(p, truth, strict=True):
        pi = min(max(pi, eps), 1 - eps)
        total -= math.log(pi) if yi == 1 else math.log(1 - pi)
    return total / len(p)


def reliability(
    p: Sequence[float], truth: Sequence[int], bins: int = BINS
) -> list[dict[str, float | int]]:
    """Per equal-width bin: count, mean predicted value and share of attacks."""
    rows = []
    for i in range(bins):
        low, high = i / bins, (i + 1) / bins
        members = [
            (pi, yi)
            for pi, yi in zip(p, truth, strict=True)
            if low <= pi < high or (i == bins - 1 and pi == 1.0)
        ]
        if members:
            rows.append(
                {
                    "bin_low": low,
                    "bin_high": high,
                    "count": len(members),
                    "mean_predicted": sum(m[0] for m in members) / len(members),
                    "attack_share": sum(m[1] for m in members) / len(members),
                }
            )
    return rows


def ece(p: Sequence[float], truth: Sequence[int], bins: int = BINS) -> float:
    """Expected calibration error: bin-weighted |mean predicted - attack share|."""
    return sum(
        row["count"] / len(p) * abs(row["mean_predicted"] - row["attack_share"])
        for row in reliability(p, truth, bins)
    )


def auc(p: Sequence[float], truth: Sequence[int]) -> float | None:
    """Area under the ROC curve; None when one class is missing."""
    pos = [pi for pi, yi in zip(p, truth, strict=True) if yi == 1]
    neg = [pi for pi, yi in zip(p, truth, strict=True) if yi == 0]
    if not pos or not neg:
        return None
    wins = sum((1.0 if a > b else 0.5 if a == b else 0.0) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def measures(p: Sequence[float], truth: Sequence[int]) -> dict[str, float | int | None]:
    return {
        "groups": len(p),
        "attacks": sum(truth),
        "brier": brier(p, truth),
        "log_loss": log_loss(p, truth),
        "ece": ece(p, truth),
        "auc": auc(p, truth),
    }


def time_blocks(datasets: Sequence[str], starts: Sequence[str], folds: int = 5) -> list[int]:
    """Fold of each group: contiguous time blocks within each dataset (RV1-D5: split by file,
    day or scenario, never by random rows). `starts` are ISO times, which sort as text."""
    if folds < 2:
        raise ValueError("folds must be at least 2")
    fold_of = [0] * len(datasets)
    for dataset in set(datasets):
        members = sorted((starts[i], i) for i in range(len(datasets)) if datasets[i] == dataset)
        for rank, (_, i) in enumerate(members):
            fold_of[i] = rank * folds // len(members)
    return fold_of


def cross_validated(
    p_raw: Sequence[float],
    truth: Sequence[int],
    folds: int = 5,
    eps: float = EPS,
    fold_of: Sequence[int] | None = None,
) -> list[float]:
    """Out-of-fold calibrated values: group i is calibrated by a fit that never saw it.

    `fold_of` gives each group's fold (use `time_blocks`); without it, folds are index blocks in
    the given order. A fold whose training part misses a class keeps p_raw for its groups.
    """
    if folds < 2:
        raise ValueError("folds must be at least 2")
    if fold_of is None:
        fold_of = [i * folds // max(len(p_raw), 1) for i in range(len(p_raw))]
    if len(fold_of) != len(p_raw):
        raise ValueError("one fold per group")
    out = list(p_raw)
    for k in range(folds):
        train = [i for i in range(len(p_raw)) if fold_of[i] != k]
        test = [i for i in range(len(p_raw)) if fold_of[i] == k]
        if not test:
            continue
        try:
            a, b = fit_platt([p_raw[i] for i in train], [truth[i] for i in train], eps)
        except ValueError:
            continue
        for i in test:
            out[i] = sigmoid(a * logit(p_raw[i], eps) + b)
    return out
