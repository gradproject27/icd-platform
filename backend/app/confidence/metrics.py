"""Measures for the confidence classifier (design 9A.2 pass marks: ECE <= 0.05, AUC >= 0.95)."""

from typing import Any

import numpy as np

ECE_BINS = 15


def reliability(y: np.ndarray, p: np.ndarray, bins: int = ECE_BINS) -> list[dict[str, Any]]:
    """Equal-width bins of predicted probability: count, mean prediction, observed rate."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.clip(np.digitize(p, edges[1:-1], right=True), 0, bins - 1)
    out = []
    for b in range(bins):
        mask = index == b
        n = int(mask.sum())
        out.append(
            {
                "low": float(edges[b]),
                "high": float(edges[b + 1]),
                "count": n,
                "mean_predicted": float(p[mask].mean()) if n else None,
                "observed_rate": float(y[mask].mean()) if n else None,
            }
        )
    return out


def ece(y: np.ndarray, p: np.ndarray, bins: int = ECE_BINS) -> float:
    """Expected calibration error: count-weighted |observed rate - mean prediction|."""
    total = len(y)
    if total == 0:
        return float("nan")
    gap = 0.0
    for row in reliability(y, p, bins):
        if row["count"]:
            gap += row["count"] / total * abs(row["observed_rate"] - row["mean_predicted"])
    return float(gap)


def summary(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    """AUC, Brier score, ECE and counts. AUC is None when only one class is present."""
    from sklearn.metrics import brier_score_loss, roc_auc_score

    y = np.asarray(y, dtype=np.int8)
    p = np.asarray(p, dtype=np.float64)
    both = 0 < int(y.sum()) < len(y)
    return {
        "rows": int(len(y)),
        "attacks": int(y.sum()),
        "auc": float(roc_auc_score(y, p)) if both else None,
        "brier": float(brier_score_loss(y, p)) if len(y) else None,
        "ece": ece(y, p),
        "reliability": reliability(y, p),
    }
