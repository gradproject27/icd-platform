"""Correlation engine v0 (C3): events -> incidents. The risk score is added by T2-09."""

from app.correlation.config import CorrelationConfig, load_config
from app.correlation.engine import (
    CorrelationResult,
    correlate,
    incident_id_for,
    incident_type_for,
)

__all__ = [
    "CorrelationConfig",
    "CorrelationResult",
    "correlate",
    "incident_id_for",
    "incident_type_for",
    "load_config",
]
