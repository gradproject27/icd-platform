"""Correlation configuration, read from correlation.toml with the standard library (no new deps)."""

import tomllib
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from app.contracts import LinkKey

DEFAULT_CONFIG_PATH = Path(__file__).with_name("correlation.toml")


@dataclass(frozen=True)
class CorrelationConfig:
    config_version: str = "correlation-v0"
    window: timedelta = timedelta(minutes=15)
    escalated_window: timedelta = timedelta(minutes=30)
    escalation_min_stage: int = 2
    keys: tuple[LinkKey, ...] = (LinkKey.HOST, LinkKey.IP_PAIR, LinkKey.USER)
    denied_hosts: frozenset[str] = frozenset()
    denied_ips: frozenset[str] = frozenset()
    denied_users: frozenset[str] = frozenset()
    stage_names: dict[int, str] = field(default_factory=dict)
    attack_type_stages: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.window <= timedelta(0):
            raise ValueError("window must be positive")
        if self.escalated_window < self.window:
            raise ValueError("escalated_window must not be shorter than window")

    def stage(self, attack_type: str | None) -> int:
        """Kill-chain stage of a dataset attack type; 0 when unknown or missing."""
        if attack_type is None:
            return 0
        return self.attack_type_stages.get(attack_type, 0)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> CorrelationConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    deny = raw.get("key_denylist", {})
    chain = raw.get("kill_chain", {})
    return CorrelationConfig(
        config_version=raw["config_version"],
        window=timedelta(minutes=raw["window_minutes"]),
        escalated_window=timedelta(minutes=raw["escalated_window_minutes"]),
        escalation_min_stage=raw["escalation_min_stage"],
        keys=tuple(LinkKey(k) for k in raw["keys"]),
        denied_hosts=frozenset(v.strip().lower() for v in deny.get("host", [])),
        denied_ips=frozenset(deny.get("ip", [])),
        denied_users=frozenset(v.strip().casefold() for v in deny.get("user", [])),
        stage_names={int(k): v for k, v in chain.get("stage_names", {}).items()},
        attack_type_stages=dict(chain.get("attack_types", {})),
    )
