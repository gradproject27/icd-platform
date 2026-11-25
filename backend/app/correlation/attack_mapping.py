"""Reviewed dataset label -> MITRE ATT&CK mapping per dataset (risk-v1 step 2, RV1-D8, RV1-D9).

Data only for now: nothing in correlation or the risk score reads it yet. Step 6 (risk-v1) reads
the stages from here instead of correlation.toml. Deterministic: the model never chooses a
technique, a tactic or a stage, and never sees these files (grounding check G3 is unchanged).
ATT&CK is (c) The MITRE Corporation (THIRD_PARTY_NOTICES.md).
"""

import re
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.correlation.tactics import TacticsConfig, load_tactics_config

MAPS_DIR = Path(__file__).with_name("attack_maps")
STAGES_PATH = MAPS_DIR / "tactic-stages.toml"
TECHNIQUE_ID = re.compile(r"T\d{4}(\.\d{3})?")
STAGES = range(1, 6)


class MappingQuality(StrEnum):
    EXACT = "exact"
    PARTIAL = "partial"
    CATEGORY_ONLY = "category-only"


@dataclass(frozen=True)
class LabelMapping:
    label: str
    techniques: tuple[tuple[str, str], ...]  # (technique ID, name)
    tactics: tuple[str, ...]
    stage: int
    quality: MappingQuality
    covers: str | None = None


@dataclass(frozen=True)
class DatasetMapping:
    dataset_id: str
    config_version: str
    attack_version: str
    source: str
    labels: dict[str, LabelMapping]

    def get(self, label: str | None) -> LabelMapping | None:
        return None if label is None else self.labels.get(label)


@dataclass(frozen=True)
class TacticStages:
    config_version: str
    attack_version: str
    stages: dict[str, int]

    def stage_of(self, tactics: tuple[str, ...]) -> int | None:
        """Highest stage among the tactics; None when there are none."""
        return max((self.stages[t] for t in tactics), default=None)


def load_tactic_stages(path: Path = STAGES_PATH) -> TacticStages:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    stages = {k: int(v) for k, v in raw["stages"].items()}
    bad = {k: v for k, v in stages.items() if v not in STAGES}
    if bad:
        raise ValueError(f"stages must be 1 to 5: {bad}")
    return TacticStages(raw["config_version"], raw["attack_version"], stages)


def load_dataset_mapping(
    path: Path,
    stages: TacticStages | None = None,
    tactics: TacticsConfig | None = None,
) -> DatasetMapping:
    """Read and check one dataset's file against the tactic list and the tactic -> stage rule."""
    stages = stages or load_tactic_stages()
    tactics = tactics or load_tactics_config()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw["attack_version"] != stages.attack_version:
        raise ValueError(f"{path.name}: ATT&CK {raw['attack_version']} != {stages.attack_version}")
    labels: dict[str, LabelMapping] = {}
    for label, row in raw["labels"].items():
        where = f"{path.name} [{label}]"
        techniques = tuple((str(t[0]), str(t[1])) for t in row["techniques"])
        for tid, name in techniques:
            if not TECHNIQUE_ID.fullmatch(tid) or not name.strip():
                raise ValueError(f"{where}: bad technique {tid!r} {name!r}")
        ids = tuple(row["tactics"])
        unknown = [t for t in ids if t not in tactics.tactics or t not in stages.stages]
        if unknown or len(set(ids)) != len(ids):
            raise ValueError(f"{where}: unknown or repeated tactic {ids}")
        quality = MappingQuality(row["quality"])
        stage = int(row["stage"])
        if stage not in STAGES:
            raise ValueError(f"{where}: stage {stage} not 1 to 5")
        if quality == MappingQuality.CATEGORY_ONLY:
            if ids or techniques:
                raise ValueError(f"{where}: category-only rows name no tactic or technique")
        else:
            if not ids or not techniques:
                raise ValueError(f"{where}: {quality} rows name a tactic and a technique")
            if stage != stages.stage_of(ids):
                raise ValueError(f"{where}: stage {stage} != {stages.stage_of(ids)} from tactics")
        labels[label] = LabelMapping(label, techniques, ids, stage, quality, row.get("covers"))
    return DatasetMapping(
        raw["dataset_id"], raw["config_version"], raw["attack_version"], raw["source"], labels
    )


def load_all() -> dict[str, DatasetMapping]:
    """Every dataset file in attack_maps/, by dataset_id."""
    stages, tactics = load_tactic_stages(), load_tactics_config()
    maps = [
        load_dataset_mapping(p, stages, tactics)
        for p in sorted(MAPS_DIR.glob("*.toml"))
        if p != STAGES_PATH
    ]
    return {m.dataset_id: m for m in maps}
