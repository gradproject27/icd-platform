"""Timed simulated containment: a simulated IP block that ends on its own (P2, decision D5).

The idea comes from Wazuh's stateful active response, which reverts an action when its timeout
expires and gives repeat offenders longer timeouts (competitor feature study, PR #51, section F-B).
This is a clean-room re-implementation on ICD's own rules; no Wazuh code was used.

- Only the IP block of a succeeded S2 is timed. Isolation and a disabled account are not.
- The same IP blocked again while its block is active extends that block (never shortens it).
- A block that starts at most `repeat_lookback` after the IP's previous block ended is a repeat:
  it uses the next duration of the list.
- Everything is simulated. A revert is an audit record and a row update; nothing real changes.

The engine (engine.py) writes and reverts the rows; this module holds the configuration and the
read model.
"""

import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_CONTAINMENT_CONFIG_PATH = Path(__file__).with_name("containment.toml")
BLOCK_IP = "block_ip"
REVERT_TRIGGER = "containment_expiry"


@dataclass(frozen=True)
class ContainmentConfig:
    config_version: str
    block_ip_minutes: tuple[int, ...]

    def __post_init__(self) -> None:
        if any(m <= 0 for m in self.block_ip_minutes):
            raise ValueError("block_ip minutes must be greater than 0")
        if list(self.block_ip_minutes) != sorted(self.block_ip_minutes):
            raise ValueError("block_ip minutes must never decrease")

    @property
    def enabled(self) -> bool:
        return bool(self.block_ip_minutes)

    @property
    def repeat_lookback(self) -> timedelta:
        """How soon after the previous block ended a new block counts as a repeat."""
        return timedelta(minutes=max(self.block_ip_minutes, default=0))

    def duration_for(self, offence: int) -> timedelta:
        """Duration of the offence-th block of an IP (1 = first); the last value repeats."""
        if not self.enabled:
            raise ValueError("timed blocks are turned off")
        if offence < 1:
            raise ValueError("offence starts at 1")
        index = min(offence, len(self.block_ip_minutes)) - 1
        return timedelta(minutes=self.block_ip_minutes[index])


def load_containment_config(path: Path = DEFAULT_CONTAINMENT_CONFIG_PATH) -> ContainmentConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return ContainmentConfig(
        config_version=raw["config_version"],
        block_ip_minutes=tuple(int(m) for m in raw["block_ip"]["minutes"]),
    )


@dataclass(frozen=True)
class Containment:
    """One simulated containment as stored (table simulated_containments)."""

    containment_id: str
    kind: str
    target: str
    incident_id: str
    action_id: str
    last_incident_id: str
    last_action_id: str
    offence: int
    extended: int
    started_at: datetime
    ends_at: datetime
    status: str
    reverted_at: datetime | None
    config_version: str
    simulated: bool
