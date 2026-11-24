"""Pairwise grouping metrics over flagged events (docs/correlation-and-risk-design.md §14.2, §14.3).

A pair of flagged events is predicted-related when both are in the same incident and truly
related when both are in the same ground-truth incident. The counts come from the contingency
table of (incident, ground-truth incident), so no pair is ever listed: n events cost O(n).
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


def _pairs(n: int) -> int:
    return n * (n - 1) // 2


@dataclass(frozen=True)
class GroupingMetrics:
    flagged_events: int
    incidents: int
    truth_incidents: int
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    incorrect_merges: int  # incidents mixing flagged events of 2+ ground-truth incidents
    missed_groups: int  # ground-truth incidents split over 2+ incidents
    alert_compression: float | None  # flagged events per incident (FR-12)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def grouping_metrics(predicted: Mapping[str, str], truth: Mapping[str, str]) -> GroupingMetrics:
    """predicted and truth map each flagged event ID to its incident / ground-truth incident.

    Both must cover exactly the same events (every flagged event is in one incident, §14.4).
    """
    if predicted.keys() != truth.keys():
        missing = len(truth.keys() - predicted.keys())
        extra = len(predicted.keys() - truth.keys())
        raise ValueError(f"event sets differ: {missing} only in truth, {extra} only in predicted")

    cells: Counter[tuple[str, str]] = Counter((predicted[e], truth[e]) for e in predicted)
    sizes_pred: Counter[str] = Counter(predicted.values())
    sizes_true: Counter[str] = Counter(truth.values())
    tp = sum(_pairs(n) for n in cells.values())
    pred_pairs = sum(_pairs(n) for n in sizes_pred.values())
    true_pairs = sum(_pairs(n) for n in sizes_true.values())
    fp, fn = pred_pairs - tp, true_pairs - tp

    truths_in: dict[str, set[str]] = defaultdict(set)
    preds_in: dict[str, set[str]] = defaultdict(set)
    for p, t in cells:
        truths_in[p].add(t)
        preds_in[t].add(p)

    precision = tp / pred_pairs if pred_pairs else None
    recall = tp / true_pairs if true_pairs else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    return GroupingMetrics(
        flagged_events=len(predicted),
        incidents=len(sizes_pred),
        truth_incidents=len(sizes_true),
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        incorrect_merges=sum(1 for ts in truths_in.values() if len(ts) > 1),
        missed_groups=sum(1 for ps in preds_in.values() if len(ps) > 1),
        alert_compression=len(predicted) / len(sizes_pred) if sizes_pred else None,
    )
