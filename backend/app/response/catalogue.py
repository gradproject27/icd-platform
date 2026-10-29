"""Catalogue lookup (OD-20, FR-44; response spec section 9).

The same deterministic lookup gives the recommendation on entry to Awaiting Human Decision and the
selection when a window expires. It never reads the AI report's free text (C-10).
"""

from dataclasses import dataclass

from app.contracts import ScenarioId
from app.response.config import ResponseConfig, Scenario
from app.response.targets import Targets

JsonScalar = str | int | float | bool | None


def confidence_band(confidence: float | None, config: ResponseConfig) -> str:
    """high (at least the threshold), low, or none when there is no valid analysis."""
    if confidence is None:
        return "none"
    return "high" if confidence >= config.confidence_threshold else "low"


def missing_needs(scenario: Scenario, targets: Targets) -> list[str]:
    """What the scenario needs that the incident does not have. Every scenario needs a host."""
    have = {"host": targets.host, "source_ip": targets.source_ip, "account": targets.account}
    return [need for need in ("host", *sorted(scenario.needs)) if have[need] is None]


@dataclass(frozen=True)
class Lookup:
    scenario_id: ScenarioId | None
    inputs: dict[str, JsonScalar]


def lookup(
    targets: Targets,
    *,
    incident_type: str | None,
    confidence: float | None,
    config: ResponseConfig,
) -> Lookup:
    """The first scenario in selection order whose needs are met, or None (no match).

    It reads only stored values (targets, type, confidence), so the expiry worker gets the same
    answer as the recommendation made when the incident entered Awaiting Human Decision.
    """
    inputs: dict[str, JsonScalar] = {
        "incident_type": incident_type,
        "confidence_band": confidence_band(confidence, config),
        "host_present": targets.host is not None,
        "source_ip_present": targets.source_ip is not None,
        "account_present": targets.account is not None,
        "config_version": config.config_version,
    }
    for scenario_id in config.selection_order:
        if not missing_needs(config.scenarios[scenario_id], targets):
            return Lookup(scenario_id, inputs)
    return Lookup(None, inputs)
