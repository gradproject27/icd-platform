"""Scenario metadata: each simulated scenario's impact and how it is reverted (P6).

From the idea of the per-action metadata (impact, reversible) of Elastic's AlertZero (competitor
feature study, PR #51, section F-E), re-implemented. Display only: the catalogue selection, the
freeze gate and the executor never read it.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.contracts import ScenarioId

DEFAULT_SCENARIO_META_PATH = Path(__file__).with_name("scenario_meta.toml")
IMPACTS = ("low", "medium", "high")


@dataclass(frozen=True)
class ScenarioMeta:
    impact: str
    reversible: bool
    revert: str  # how the simulated effect ends, in plain words

    def __post_init__(self) -> None:
        if self.impact not in IMPACTS:
            raise ValueError(f"impact must be one of {IMPACTS}, not {self.impact!r}")
        if not self.revert.strip():
            raise ValueError("revert must say how the scenario is reverted")


@dataclass(frozen=True)
class ScenarioMetaConfig:
    config_version: str
    scenarios: dict[ScenarioId, ScenarioMeta]


def load_scenario_meta(path: Path = DEFAULT_SCENARIO_META_PATH) -> ScenarioMetaConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    scenarios = {
        ScenarioId(key): ScenarioMeta(value["impact"], bool(value["reversible"]), value["revert"])
        for key, value in raw["scenarios"].items()
    }
    missing = sorted(s.value for s in set(ScenarioId) - set(scenarios))
    if missing:
        raise ValueError(f"metadata missing for {missing}")
    return ScenarioMetaConfig(raw["config_version"], scenarios)
