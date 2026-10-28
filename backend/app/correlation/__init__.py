"""Correlation engine v0 (C3): events -> incidents, plus risk levels. The score comes in T2-09."""

from app.correlation.config import CorrelationConfig, load_config
from app.correlation.engine import (
    CorrelationResult,
    correlate,
    incident_id_for,
    incident_type_for,
)
from app.correlation.levels import RiskThresholds, check_level, is_high, level_for

__all__ = [
    "CorrelationConfig",
    "CorrelationResult",
    "RiskThresholds",
    "check_level",
    "correlate",
    "incident_id_for",
    "incident_type_for",
    "is_high",
    "level_for",
    "load_config",
]
