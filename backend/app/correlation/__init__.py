"""Correlation engine v0 and risk score v0 (C3): events -> incidents -> scored incidents."""

from app.correlation.config import CorrelationConfig, load_config
from app.correlation.engine import (
    CorrelationResult,
    correlate,
    incident_id_for,
    incident_type_for,
)
from app.correlation.levels import RiskThresholds, check_level, is_high, level_for
from app.correlation.risk import RiskConfig, load_risk_config, score_incident, score_incidents

__all__ = [
    "CorrelationConfig",
    "CorrelationResult",
    "RiskConfig",
    "RiskThresholds",
    "check_level",
    "correlate",
    "incident_id_for",
    "incident_type_for",
    "is_high",
    "level_for",
    "load_config",
    "load_risk_config",
    "score_incident",
    "score_incidents",
]
