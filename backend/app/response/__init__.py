"""Response engine v0 (C5): lifecycle, freeze check, catalogue lookup, simulated executor.

Every response action is a simulation. Nothing in this package can reach a real host.
"""

from app.response.catalogue import Lookup, confidence_band, lookup, missing_needs
from app.response.config import ResponseConfig, Scenario, load_response_config
from app.response.executor import (
    SIMULATED_LABEL,
    MissingTarget,
    SimulationResult,
    decide,
    execute,
    never_fail,
    propose,
)
from app.response.freeze import FreezeCheck, NoFreezeReason, check_freeze, report_valid
from app.response.lifecycle import (
    TRANSITIONS,
    Transition,
    TransitionRefused,
    Trigger,
    transition_for,
)
from app.response.targets import Targets, find_targets, flagged_events

__all__ = [
    "SIMULATED_LABEL",
    "TRANSITIONS",
    "FreezeCheck",
    "Lookup",
    "MissingTarget",
    "NoFreezeReason",
    "ResponseConfig",
    "Scenario",
    "SimulationResult",
    "Targets",
    "Transition",
    "TransitionRefused",
    "Trigger",
    "check_freeze",
    "confidence_band",
    "decide",
    "execute",
    "find_targets",
    "flagged_events",
    "load_response_config",
    "lookup",
    "missing_needs",
    "never_fail",
    "propose",
    "report_valid",
    "transition_for",
]
