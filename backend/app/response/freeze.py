"""Freeze preconditions (FR-43, NFR-SF-06, OD-16, OD-17; response spec section 5).

An incident freezes only when every precondition holds. The check returns every failing reason,
so the audit record and the tests can say exactly why an incident did not freeze.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.contracts import AnalysisStatus, Incident
from app.correlation import is_high
from app.response.config import ResponseConfig
from app.response.targets import Targets


class NoFreezeReason(StrEnum):
    ANALYSIS_NOT_VALID = "analysis_not_valid"  # precondition 1 (OD-09)
    RISK_NOT_HIGH = "risk_not_high"  # precondition 2 (OD-05); also when not scored yet
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"  # precondition 3 (OD-16)
    WINDOW_ALREADY_OPEN = "window_already_open"  # precondition 4 (OD-17)
    NO_TARGET_HOST = "no_target_host"  # decision D3: a freeze must isolate a host


@dataclass(frozen=True)
class FreezeCheck:
    reasons: tuple[NoFreezeReason, ...]

    @property
    def freeze(self) -> bool:
        return not self.reasons

    def as_details(self) -> dict[str, str | bool]:
        return {"freeze": self.freeze, "reasons": ",".join(r.value for r in self.reasons)}


def report_valid(incident: Incident) -> bool:
    """Decision D2: a valid analysis is a succeeded analysis with a stored report.

    The Incident contract sets confidence exactly when the analysis succeeded, so a failed or
    missing analysis never has a confidence and can never pass precondition 3 either.
    """
    return (
        incident.analysis_status == AnalysisStatus.SUCCEEDED
        and incident.latest_report_id is not None
    )


def check_freeze(
    incident: Incident, targets: Targets, *, window_open: bool, config: ResponseConfig
) -> FreezeCheck:
    """Every precondition that fails; none means the incident freezes."""
    reasons = []
    if not report_valid(incident):
        reasons.append(NoFreezeReason.ANALYSIS_NOT_VALID)
    if not is_high(incident.risk):
        reasons.append(NoFreezeReason.RISK_NOT_HIGH)
    if incident.confidence is None or incident.confidence < config.confidence_threshold:
        reasons.append(NoFreezeReason.CONFIDENCE_BELOW_THRESHOLD)
    if window_open:
        reasons.append(NoFreezeReason.WINDOW_ALREADY_OPEN)
    if targets.host is None:
        reasons.append(NoFreezeReason.NO_TARGET_HOST)
    return FreezeCheck(tuple(reasons))
