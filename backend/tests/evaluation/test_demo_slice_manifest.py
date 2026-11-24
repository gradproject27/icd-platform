"""The committed demo slice manifest (C2-D17, C2-D18): consistent, and holds no address."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "fixtures" / "demo"
IP = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def manifest():
    return json.loads((DEMO / "unsw-nb15-demo-slice.json").read_text(encoding="utf-8"))


def test_checksum_file_matches_the_manifest():
    digest, name = (DEMO / "unsw-nb15-demo-slice.sha256").read_text().split()
    m = manifest()
    assert (digest, name) == (m["slice_sha256"], m["slice_file"])
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_slice_gives_a_high_and_a_medium_incident():
    m = manifest()
    assert m["levels"].get("high", 0) >= 1 and m["levels"].get("medium", 0) >= 1
    assert sum(m["levels"].values()) == m["incidents"] == len(m["expected_incidents"])
    assert m["events"] == m["lines"] == m["flagged"] + m["unflagged"] + m["unlabelled"]
    assert m["start_epoch"] <= m["end_epoch"] and m["lines"] <= 5000


def test_no_dataset_row_or_address_is_committed():
    for path in DEMO.iterdir():
        assert path.suffix in {".json", ".sha256", ".md"}, path.name
        assert not IP.search(path.read_text(encoding="utf-8")), path.name
