"""Response engine configuration (response.toml): freeze gate, internal networks, catalogue v0."""

import ipaddress
import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.contracts import ScenarioId

DEFAULT_RESPONSE_CONFIG_PATH = Path(__file__).with_name("response.toml")

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
NEEDS = frozenset({"source_ip", "account"})


@dataclass(frozen=True)
class Scenario:
    scenario_id: ScenarioId
    title: str
    needs: frozenset[str]
    automatic: bool


@dataclass(frozen=True)
class ResponseConfig:
    config_version: str
    confidence_threshold: float
    window_seconds: int
    internal_networks: tuple[Network, ...]
    scenarios: dict[ScenarioId, Scenario]
    selection_order: tuple[ScenarioId, ...]

    def __post_init__(self) -> None:
        if not 0 < self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be in (0, 1]")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be greater than 0")
        if set(self.scenarios) != set(ScenarioId):
            raise ValueError("the catalogue must define exactly S1, S2, S3 and S4")
        for scenario_id in self.selection_order:
            if not self.scenarios[scenario_id].automatic:
                raise ValueError(f"{scenario_id} is not automatic, so it cannot be selected")

    def is_internal(self, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(address in network for network in self.internal_networks)


def load_response_config(path: Path = DEFAULT_RESPONSE_CONFIG_PATH) -> ResponseConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    scenarios = {}
    for key, value in raw["scenarios"].items():
        needs = frozenset(value["needs"])
        if not needs <= NEEDS:
            raise ValueError(f"{key}: unknown needs {sorted(needs - NEEDS)}")
        scenario_id = ScenarioId(key)
        scenarios[scenario_id] = Scenario(scenario_id, value["title"], needs, value["automatic"])
    return ResponseConfig(
        config_version=raw["config_version"],
        confidence_threshold=float(raw["freeze"]["confidence_threshold"]),
        window_seconds=int(raw["freeze"]["window_seconds"]),
        internal_networks=tuple(ipaddress.ip_network(n) for n in raw["network"]["internal"]),
        scenarios=scenarios,
        selection_order=tuple(ScenarioId(s) for s in raw["selection"]["order"]),
    )
