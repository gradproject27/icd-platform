"""Reviewed dataset label -> ATT&CK mapping (risk-v1 step 2, decisions RV1-D8 and RV1-D9)."""

from pathlib import Path

import pytest

from app.correlation import load_config
from app.correlation.attack_mapping import (
    MappingQuality,
    load_all,
    load_dataset_mapping,
    load_tactic_stages,
)
from app.correlation.tactics import load_tactics_config

MAPS = load_all()
STAGES = load_tactic_stages()


def test_every_dataset_file_loads():
    assert set(MAPS) == {"unsw-nb15", "nf-cse-cic-ids2018-v3", "otrf"}
    assert {m.attack_version for m in MAPS.values()} == {"20.1"}


def test_every_tactic_has_a_stage():
    assert set(STAGES.stages) == set(load_tactics_config().tactics)


def test_unsw_tactics_match_p4_table():
    p4 = load_tactics_config().attack_types
    unsw = MAPS["unsw-nb15"].labels
    assert set(unsw) == set(p4)
    for label, row in unsw.items():
        assert row.tactics == p4[label], label


def test_unsw_covers_every_attack_type_of_correlation_config():
    assert set(load_config().attack_type_stages) == set(MAPS["unsw-nb15"].labels)


def test_correlation_config_follows_the_attack_map_stages():
    # Decision of 25 Nov 2026: follow ATT&CK for Shellcode (3 -> 2), applied in step 6a.
    today = load_config().attack_type_stages
    changed = {
        label: (today[label], row.stage)
        for label, row in MAPS["unsw-nb15"].labels.items()
        if today[label] != row.stage
    }
    assert changed == {}


def test_generic_and_analysis_keep_their_stage_as_category_only():
    unsw = MAPS["unsw-nb15"].labels
    assert unsw["Generic"].quality == MappingQuality.CATEGORY_ONLY
    assert unsw["Analysis"].quality == MappingQuality.CATEGORY_ONLY
    assert (unsw["Generic"].stage, unsw["Analysis"].stage) == (2, 1)


def test_cic_classes_as_on_the_dataset_page():
    assert set(MAPS["nf-cse-cic-ids2018-v3"].labels) == {
        "BruteForce", "Bot", "DoS", "DDoS", "Infiltration", "Web Attacks",
    }  # fmt: skip


def test_get_unknown_label():
    assert MAPS["unsw-nb15"].get("Nope") is None
    assert MAPS["unsw-nb15"].get(None) is None


def _row(techniques: str, tactics: str, stage: int, quality: str) -> str:
    return (
        f"[labels.A]\ntechniques = {techniques}\ntactics = {tactics}\n"
        f'stage = {stage}\nquality = "{quality}"\n'
    )


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "x.toml"
    path.write_text(
        'dataset_id = "x"\nconfig_version = "x-v1"\nattack_version = "20.1"\nsource = "s"\n' + body,
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "body",
    [
        _row('[["T1190", "n"]]', '["TA0001"]', 3, "exact"),  # stage disagrees with tactic rule
        _row('[["T1190", "n"]]', '["TA9999"]', 2, "exact"),  # unknown tactic
        _row('[["X1190", "n"]]', '["TA0001"]', 2, "exact"),  # bad technique ID
        _row("[]", '["TA0001"]', 2, "category-only"),  # category-only with a tactic
        _row("[]", '["TA0001"]', 2, "partial"),  # mapped row without a technique
        _row("[]", "[]", 6, "category-only"),  # stage out of range
    ],
)
def test_bad_rows_are_refused(tmp_path, body):
    with pytest.raises(ValueError):
        load_dataset_mapping(_write(tmp_path, body))


def test_highest_stage_wins():
    assert STAGES.stage_of(("TA0002", "TA0007")) == 2
    assert STAGES.stage_of(("TA0003", "TA0011")) == 3
    assert STAGES.stage_of(()) is None
