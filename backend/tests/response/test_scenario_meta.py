"""Scenario metadata: impact and how each simulated scenario is reverted (P6 of the competitor
feature study, F-E: AlertZero's per-action impact, reversible and approval metadata).

Kept in scenario_meta.toml so response.toml (response-v1) and the catalogue selection stay as they
are. Display only: nothing reads it to select, approve or run a scenario.
"""

from pathlib import Path

import pytest

from app.contracts import ScenarioId
from app.response.scenario_meta import (
    DEFAULT_SCENARIO_META_PATH,
    ScenarioMeta,
    load_scenario_meta,
)


def test_shipped_metadata():
    meta = load_scenario_meta()
    assert meta.config_version == "scenario-meta-v1"
    assert set(meta.scenarios) == set(ScenarioId)
    assert {s: (m.impact, m.reversible) for s, m in meta.scenarios.items()} == {
        ScenarioId.S1: ("medium", True),
        ScenarioId.S2: ("high", True),
        ScenarioId.S3: ("high", True),
        ScenarioId.S4: ("low", True),
    }
    # The IP block of S2 ends on its own (P2); isolation and accounts need an analyst.
    assert "ends on its own" in meta.scenarios[ScenarioId.S2].revert
    assert "analyst" in meta.scenarios[ScenarioId.S3].revert


def test_every_scenario_needs_metadata(tmp_path: Path):
    path = tmp_path / "meta.toml"
    path.write_text(
        'config_version = "x"\n[scenarios.S1]\nimpact = "low"\nreversible = true\nrevert = "r"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="S2"):
        load_scenario_meta(path)


@pytest.mark.parametrize(("impact", "revert"), [("severe", "r"), ("low", "")])
def test_invalid_metadata_is_refused(impact, revert):
    with pytest.raises(ValueError):
        ScenarioMeta(impact=impact, reversible=True, revert=revert)


def test_file_sits_next_to_the_response_config():
    assert DEFAULT_SCENARIO_META_PATH.with_name("response.toml").exists()
