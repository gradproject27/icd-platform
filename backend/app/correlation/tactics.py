"""Dataset attack type -> MITRE ATT&CK tactics, from a reviewed table (tactics.toml, P4).

Deterministic: the same attack type always gives the same tactics, matched exactly like the
correlation config's kill-chain stages. The model never chooses a tactic and never sees this
table. ATT&CK is (c) The MITRE Corporation (THIRD_PARTY_NOTICES.md).
"""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TACTICS_PATH = Path(__file__).with_name("tactics.toml")
TACTIC_ID = re.compile(r"TA\d{4}")


@dataclass(frozen=True)
class TacticsConfig:
    config_version: str
    tactics: dict[str, str]  # tactic ID -> name
    attack_types: dict[str, tuple[str, ...]]  # dataset attack type -> tactic IDs

    def __post_init__(self) -> None:
        for tactic_id, name in self.tactics.items():
            if not TACTIC_ID.fullmatch(tactic_id):
                raise ValueError(f"bad tactic ID {tactic_id!r}")
            if not name.strip():
                raise ValueError(f"{tactic_id}: empty name")
        for attack_type, ids in self.attack_types.items():
            if len(set(ids)) != len(ids):
                raise ValueError(f"{attack_type}: a tactic is listed twice")
            unknown = [i for i in ids if i not in self.tactics]
            if unknown:
                raise ValueError(f"{attack_type}: unknown tactic {unknown}")

    def tactics_for(self, attack_type: str | None) -> tuple[tuple[str, str], ...]:
        """(ID, name) pairs of a dataset attack type; empty when unknown or unmapped."""
        if attack_type is None:
            return ()
        return tuple((i, self.tactics[i]) for i in self.attack_types.get(attack_type, ()))


def load_tactics_config(path: Path = DEFAULT_TACTICS_PATH) -> TacticsConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return TacticsConfig(
        config_version=raw["config_version"],
        tactics=dict(raw["tactics"]),
        attack_types={k: tuple(v) for k, v in raw["attack_types"].items()},
    )
