"""What the confidence classifier sees, and how rows are split (risk-v1 step 4).

The input is the NetFlow v3 CSV layout shared by NF-UNSW-NB15-v3 and NF-CSE-CIC-IDS2018-v3
(app.ingest.nf_v3.COLUMNS, checked by the user on 25 Nov 2026).

Excluded from the features, so the model cannot learn a shortcut that does not carry over to
other networks or times:
- IPV4_SRC_ADDR, IPV4_DST_ADDR: the attacker and victim addresses of one lab;
- L4_SRC_PORT, L4_DST_PORT: ephemeral ports and the lab's service layout;
- FLOW_START_MILLISECONDS, FLOW_END_MILLISECONDS: when the lab ran each attack;
- Label, Attack: the answer.
The 47 other columns are numeric flow statistics and are all used.

Split (design 9A.4: by file, day or scenario, never by random rows). Each dataset is one file
and UNSW-NB15 spans only a few days, so flows are grouped into blocks of BLOCK_MINUTES of
start time, and each block goes as a whole to train (6 in 10), calibration (2 in 10) or test
(2 in 10) by a hash of (dataset, block). Flows next to each other in time never land in
different splits, and every split still sees several attack windows.
"""

import hashlib

from app.ingest.nf_v3 import COLUMNS

DATASETS = ("nf-unsw-nb15-v3", "nf-cse-cic-ids2018-v3")
EXCLUDED = (
    "IPV4_SRC_ADDR", "IPV4_DST_ADDR", "L4_SRC_PORT", "L4_DST_PORT",
    "FLOW_START_MILLISECONDS", "FLOW_END_MILLISECONDS", "Label", "Attack",
)  # fmt: skip
FEATURES = tuple(name for name in COLUMNS if name not in EXCLUDED)
FEATURE_SET_VERSION = "nf-v3-flow-47-v1"

BENIGN = "Benign"
SPLITS = ("train", "calibration", "test")
BLOCK_MINUTES = 60
_SPLIT_OF_BUCKET = ("train",) * 6 + ("calibration",) * 2 + ("test",) * 2


def split_of_block(dataset_id: str, block: int) -> str:
    """train, calibration or test for one time block of one dataset; stable across runs."""
    digest = hashlib.sha256(f"{dataset_id}:{block}".encode()).digest()
    return _SPLIT_OF_BUCKET[int.from_bytes(digest[:8], "big") % 10]


def block_of(start_ms: int, block_minutes: int = BLOCK_MINUTES) -> int:
    return int(start_ms) // (block_minutes * 60_000)


def class_of(label: int, attack: str | None) -> str:
    """The class a row is counted and capped under: its attack class, or Benign."""
    if label != 1:
        return BENIGN
    return (attack or "").strip() or "unknown-attack"
