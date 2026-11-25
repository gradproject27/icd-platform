"""Attack type -> MITRE ATT&CK tactic table (P4 of the competitor feature study, F-F and F-H).

A reviewed, deterministic table: the model never chooses a tactic, and the table is never given
to it (grounding check G3 stays as it is).
"""

import json
import re
from pathlib import Path

import pytest

from app.correlation import load_config
from app.correlation.tactics import (
    DEFAULT_TACTICS_PATH,
    TacticsConfig,
    load_tactics_config,
)

REPO = Path(__file__).resolve().parents[3]
TACTICS = load_tactics_config()

# Enterprise tactics in MITRE's STIX data (enterprise-attack.json, matrix modified 2026-07-31,
# read from wazuh/wazuh@6cc7b2e ruleset/mitre). TA0005 is "Stealth" there, no longer
# "Defense Evasion", and TA0112 "Defense Impairment" is new.
ENTERPRISE = {
    "TA0001": "Initial Access",
    "TA0002": "Execution",
    "TA0003": "Persistence",
    "TA0004": "Privilege Escalation",
    "TA0005": "Stealth",
    "TA0006": "Credential Access",
    "TA0007": "Discovery",
    "TA0008": "Lateral Movement",
    "TA0009": "Collection",
    "TA0010": "Exfiltration",
    "TA0011": "Command and Control",
    "TA0040": "Impact",
    "TA0042": "Resource Development",
    "TA0043": "Reconnaissance",
    "TA0112": "Defense Impairment",
}


def unsw_attack_types() -> set[str]:
    mapping = json.loads(
        (REPO / "backend/app/ingest/mappings/label-mapping.json").read_text(encoding="utf-8")
    )
    source = next(s for s in mapping["sources"] if s["dataset_id"] == "unsw-nb15")
    return {v["raw_value"] for v in source["attack_type_values"]}


def test_shipped_table_version_and_tactic_names_match_mitre():
    assert TACTICS.config_version == "tactics-v1"
    assert TACTICS.tactics == ENTERPRISE


def test_every_dataset_and_correlation_attack_type_has_a_row():
    # A row may be empty (no tactic), but an attack type is never silently missing.
    known = set(TACTICS.attack_types)
    assert unsw_attack_types() <= known
    assert set(load_config().attack_type_stages) <= known


def test_rows_reviewed_for_the_fixture_and_unsw():
    pairs = {t: [tid for tid, _ in TACTICS.tactics_for(t)] for t in TACTICS.attack_types}
    assert pairs == {
        "Reconnaissance": ["TA0043"],
        "Fuzzers": ["TA0043"],
        "Analysis": [],
        "Generic": [],
        "Exploits": ["TA0001"],
        "Shellcode": ["TA0002"],
        "Backdoors": ["TA0003", "TA0011"],
        "Backdoor": ["TA0003", "TA0011"],
        "Worms": ["TA0008"],
        "DoS": ["TA0040"],
    }


def test_unknown_or_missing_attack_type_has_no_tactic():
    assert TACTICS.tactics_for(None) == ()
    assert TACTICS.tactics_for("Something new") == ()
    # Exact match, as the correlation config: no trimming or case folding here.
    assert TACTICS.tactics_for("dos") == ()


def test_tactics_come_with_their_names():
    assert TACTICS.tactics_for("DoS") == (("TA0040", "Impact"),)


@pytest.mark.parametrize(
    ("tactics", "attack_types", "error"),
    [
        ({"TA0001": "Initial Access"}, {"X": ("TA0002",)}, "unknown tactic"),
        ({"TA01": "Bad"}, {}, "tactic ID"),
        ({"TA0001": ""}, {}, "name"),
        ({"TA0001": "Initial Access"}, {"X": ("TA0001", "TA0001")}, "twice"),
    ],
)
def test_invalid_tables_are_refused(tactics, attack_types, error):
    with pytest.raises(ValueError, match=error):
        TacticsConfig("t", tactics, attack_types)


def test_ids_are_well_formed():
    for tactic_id in TACTICS.tactics:
        assert re.fullmatch(r"TA\d{4}", tactic_id)


def test_loader_reads_another_file(tmp_path):
    path = tmp_path / "tactics.toml"
    path.write_text(
        'config_version = "x"\n[tactics]\nTA0040 = "Impact"\n[attack_types]\nDoS = ["TA0040"]\n',
        encoding="utf-8",
    )
    assert load_tactics_config(path).tactics_for("DoS") == (("TA0040", "Impact"),)
    assert DEFAULT_TACTICS_PATH.name == "tactics.toml"
