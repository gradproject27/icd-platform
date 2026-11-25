"""Timed simulated containment, configuration (P2 of the competitor feature study, PR #51, F-B).

containment.toml holds how long a simulated IP block lasts: the first block, then each repeat.
"""

from datetime import timedelta
from pathlib import Path

import pytest

from app.response.containment import (
    DEFAULT_CONTAINMENT_CONFIG_PATH,
    ContainmentConfig,
    load_containment_config,
)


def test_shipped_values_are_decision_d5():
    config = load_containment_config()
    assert config.config_version == "containment-v1"
    assert config.block_ip_minutes == (60, 120, 240)
    assert config.enabled


def test_duration_per_offence_stays_at_the_last_value():
    config = ContainmentConfig("t", (60, 120, 240))
    assert [config.duration_for(n) for n in (1, 2, 3, 4, 9)] == [
        timedelta(minutes=60),
        timedelta(minutes=120),
        timedelta(minutes=240),
        timedelta(minutes=240),
        timedelta(minutes=240),
    ]
    # A block counts as a repeat when the previous one ended at most this long before.
    assert config.repeat_lookback == timedelta(minutes=240)


def test_empty_list_turns_the_feature_off():
    config = ContainmentConfig("t", ())
    assert not config.enabled
    with pytest.raises(ValueError):
        config.duration_for(1)


@pytest.mark.parametrize(
    "minutes",
    [(0,), (-5,), (60, 30), (60, 0)],
)
def test_minutes_must_be_positive_and_never_decrease(minutes):
    with pytest.raises(ValueError):
        ContainmentConfig("t", minutes)


def test_offence_starts_at_one():
    with pytest.raises(ValueError):
        ContainmentConfig("t", (60,)).duration_for(0)


def test_loader_reads_another_file(tmp_path: Path):
    path = tmp_path / "containment.toml"
    path.write_text('config_version = "x"\n[block_ip]\nminutes = []\n', encoding="utf-8")
    assert load_containment_config(path) == ContainmentConfig("x", ())


def test_shipped_file_is_next_to_the_response_config():
    assert DEFAULT_CONTAINMENT_CONFIG_PATH.name == "containment.toml"
    assert DEFAULT_CONTAINMENT_CONFIG_PATH.with_name("response.toml").exists()
