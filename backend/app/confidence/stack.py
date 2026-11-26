"""Event confidence C from p_clf and p_llm (risk-v1 step 6a, design 9A.2 steps 4 to 6).

1. Stacking: logit(C) = a + b1 * logit(p_clf) + b2 * logit(p_llm), a logistic regression fitted
   on calibration events (the data sets the weights). Events carry their group's p_llm.
   Sample weights bring the 1:1 groups sample back to the natural attack share (the same
   prior correction as app.confidence.llm_calibrate).
2. Uncertainty: split conformal prediction at 1 - alpha = 95%. The calibration events are cut
   in two by a hash of their group, so a group is never in both halves: one half fits the
   stacker, the other gives the nonconformity scores s = 1 - P(true class). With q the
   ceil((n + 1)(1 - alpha)) / n quantile of s, the prediction set of an event holds "attack" when
   1 - C <= q and "benign" when C <= q. When it holds both (or neither), the event gets
   needs_review: the data cannot tell the label is right at 95% (Vovk et al. 2005; Angelopoulos
   and Bates 2021).
3. Range: C is clamped to [0.05, 1], so one uncertain event never erases an attack.
4. Fallback: without p_llm, C = calibrated p_clf (clamped) with flag llm_pending or
   llm_unavailable (RV1-D3); conformal needs both inputs, so no needs_review then.

Output: stacker.json (plain JSON: weights, conformal threshold, versions of the inputs).
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.confidence.values import C_MAX, C_MIN, Confidence, clamp

__all__ = ["C_MAX", "C_MIN", "Confidence", "clamp"]

STACKER_FORMAT = "icd-confidence-stacker-v1"
ALPHA = 0.05
EPS = 1e-4


def logit(p: np.ndarray | float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=np.float64), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def half_of(group_id: str) -> int:
    """0 = fit the stacker, 1 = conformal scores; stable per group."""
    return hashlib.sha256(group_id.encode()).digest()[0] & 1


def prior_weights(y: np.ndarray, natural_share: float | None) -> np.ndarray:
    """Weights that make the weighted attack share equal the natural one."""
    y = np.asarray(y, dtype=np.int8)
    sample = float(y.mean()) if len(y) else 0.0
    if natural_share is None or not 0 < natural_share < 1 or not 0 < sample < 1:
        return np.ones(len(y))
    return np.where(y == 1, natural_share / sample, (1 - natural_share) / (1 - sample))


def conformal_threshold(scores: np.ndarray, alpha: float = ALPHA) -> float:
    """The ceil((n + 1)(1 - alpha)) / n empirical quantile of the nonconformity scores."""
    scores = np.sort(np.asarray(scores, dtype=np.float64))
    n = len(scores)
    if n == 0:
        raise ValueError("no conformal scores")
    rank = math.ceil((n + 1) * (1 - alpha))
    return 1.0 if rank > n else float(scores[rank - 1])


@dataclass
class Stacker:
    a: float
    b_clf: float
    b_llm: float
    threshold: float  # conformal q
    alpha: float = ALPHA
    meta: dict[str, Any] = field(default_factory=dict)

    def raw(self, p_clf: np.ndarray, p_llm: np.ndarray) -> np.ndarray:
        z = self.a + self.b_clf * logit(p_clf) + self.b_llm * logit(p_llm)
        return 1.0 / (1.0 + np.exp(-z))

    def needs_review(self, c: float) -> bool:
        attack, benign = 1 - c <= self.threshold, c <= self.threshold
        return attack == benign  # both possible, or neither

    def to_json(self) -> dict[str, Any]:
        return {"format": STACKER_FORMAT, "a": self.a, "b_clf": self.b_clf, "b_llm": self.b_llm,
                "threshold": self.threshold, "alpha": self.alpha, **self.meta}  # fmt: skip


def combine(p_clf: float, p_llm: float | None, stacker: Stacker | None,
            llm_flag: str = "llm_pending") -> Confidence:  # fmt: skip
    """C for one event. Without p_llm or a stacker: calibrated p_clf with llm_flag."""
    if p_llm is None or stacker is None:
        return Confidence(clamp(p_clf), p_clf, p_llm, (llm_flag,))
    c = float(stacker.raw(np.array([p_clf]), np.array([p_llm]))[0])
    flags = ("needs_review",) if stacker.needs_review(c) else ()
    return Confidence(clamp(c), p_clf, p_llm, flags)


def fit(p_clf: np.ndarray, p_llm: np.ndarray, y: np.ndarray, group_ids: list[str],
        natural_share: float | None = None, alpha: float = ALPHA,
        meta: dict[str, Any] | None = None) -> tuple[Stacker, dict[str, Any]]:  # fmt: skip
    """Fit on one half of the groups, conformal on the other; returns the stacker and counts."""
    from sklearn.linear_model import LogisticRegression

    p_clf, p_llm = np.asarray(p_clf, float), np.asarray(p_llm, float)
    y = np.asarray(y, dtype=np.int8)
    half = np.array([half_of(g) for g in group_ids])
    fit_mask, conf_mask = half == 0, half == 1
    for name, mask in (("fit", fit_mask), ("conformal", conf_mask)):
        if len(np.unique(y[mask])) < 2:
            raise ValueError(f"the {name} half needs both attack and benign events")
    X = np.column_stack([logit(p_clf), logit(p_llm)])
    model = LogisticRegression(C=1e6, max_iter=1000)
    model.fit(X[fit_mask], y[fit_mask], sample_weight=prior_weights(y[fit_mask], natural_share))
    a, (b_clf, b_llm) = float(model.intercept_[0]), (float(v) for v in model.coef_[0])
    stacker = Stacker(a, b_clf, b_llm, threshold=1.0, alpha=alpha)
    c = stacker.raw(p_clf[conf_mask], p_llm[conf_mask])
    scores = np.where(y[conf_mask] == 1, 1 - c, c)
    stacker.threshold = conformal_threshold(scores, alpha)
    stacker.meta = {
        **(meta or {}),
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "fit_events": int(fit_mask.sum()),
        "conformal_events": int(conf_mask.sum()),
        "natural_attack_share": natural_share,
    }
    counts = {"fit_events": int(fit_mask.sum()), "conformal_events": int(conf_mask.sum())}
    return stacker, counts


def evaluate(stacker: Stacker, p_clf: np.ndarray, p_llm: np.ndarray,
             y: np.ndarray) -> dict[str, Any]:  # fmt: skip
    """Coverage and review share of the conformal sets, plus the step 4 measures of C."""
    from app.confidence.metrics import summary

    y = np.asarray(y, dtype=np.int8)
    c = stacker.raw(np.asarray(p_clf, float), np.asarray(p_llm, float))
    attack, benign = 1 - c <= stacker.threshold, c <= stacker.threshold
    covered = np.where(y == 1, attack, benign)
    review = attack == benign
    clamped = np.clip(c, C_MIN, C_MAX)
    return {
        "stacked": summary(y, c),
        "clamped": summary(y, clamped),
        "conformal_coverage": float(covered.mean()) if len(y) else None,
        "needs_review_share": float(review.mean()) if len(y) else None,
        "target_coverage": 1 - stacker.alpha,
    }


def save(stacker: Stacker, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stacker.to_json(), indent=2) + "\n", encoding="utf-8")


def load(path: Path) -> Stacker:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != STACKER_FORMAT:
        raise ValueError(f"{path} is not an {STACKER_FORMAT} file")
    known = ("format", "a", "b_clf", "b_llm", "threshold", "alpha")
    return Stacker(float(data["a"]), float(data["b_clf"]), float(data["b_llm"]),
                   float(data["threshold"]), float(data["alpha"]),
                   {k: v for k, v in data.items() if k not in known})  # fmt: skip
