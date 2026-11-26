"""The per-event confidence value the risk score reads (risk-v1, design 9A.2 step 6).

Kept free of NumPy and scikit-learn, so the risk code (app.correlation.risk) imports it in the
api and worker images, which do not install the model packages.
"""

from dataclasses import dataclass

C_MIN, C_MAX = 0.05, 1.0


def clamp(c: float) -> float:
    """C is kept between 0.05 and 1, so one uncertain event never erases an attack."""
    return float(min(max(c, C_MIN), C_MAX))


@dataclass(frozen=True)
class Confidence:
    """C of one event and what it rests on (for RiskContributor.reason and the audit)."""

    c: float
    p_clf: float | None
    p_llm: float | None
    flags: tuple[str, ...] = ()
