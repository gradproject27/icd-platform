"""Risk level from the risk score (OD-05, FR-20). C5's freeze rule reads the level through here.

Low is 0 to 39, Medium 40 to 69 and High 70 to 100, with the thresholds held in risk.toml. The
contract does not check that a stored level matches its score, so `check_level` does.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.contracts import RiskAssessment, RiskLevel

DEFAULT_RISK_CONFIG_PATH = Path(__file__).with_name("risk.toml")


@dataclass(frozen=True)
class RiskThresholds:
    medium: int = 40
    high: int = 70

    def __post_init__(self) -> None:
        if not 0 < self.medium < self.high <= 100:
            raise ValueError("thresholds must satisfy 0 < medium < high <= 100")

    def level_for(self, score: int) -> RiskLevel:
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise ValueError(f"score must be an integer from 0 to 100, got {score!r}")
        if score >= self.high:
            return RiskLevel.HIGH
        if score >= self.medium:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


def load_thresholds(path: Path = DEFAULT_RISK_CONFIG_PATH) -> RiskThresholds:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))["thresholds"]
    return RiskThresholds(medium=raw["medium"], high=raw["high"])


THRESHOLDS = load_thresholds()


def level_for(score: int) -> RiskLevel:
    """The level of a score under the configured thresholds."""
    return THRESHOLDS.level_for(score)


def is_high(risk: RiskAssessment | None) -> bool:
    """Freeze precondition 2: the incident is scored and High. Not scored yet is not High."""
    return risk is not None and risk.level == RiskLevel.HIGH


def check_level(risk: RiskAssessment) -> None:
    """Raise when a stored level does not match its score (the contract leaves this to C3)."""
    expected = level_for(risk.score)
    if risk.level != expected:
        raise ValueError(f"score {risk.score} is {expected.value}, but the level is {risk.level}")
