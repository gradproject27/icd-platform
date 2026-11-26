"""Step 4 pipeline on invented NetFlow v3 rows (no dataset row is in git)."""

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pyarrow")

from app.confidence import features as F  # noqa: E402
from app.confidence.metrics import ece, reliability, summary  # noqa: E402
from app.confidence.prepare import main as prepare_main  # noqa: E402
from app.confidence.prepare import prepare, rates  # noqa: E402
from app.confidence.train import load, run  # noqa: E402
from app.ingest.nf_v3 import COLUMNS  # noqa: E402

T0 = 1421927414000  # 22 Jan 2015, as in the ingest fixtures
HOURS = 72


def write_csv(path: Path, attacks: tuple[str, ...], rows: int, seed: int, shift: float = 0.0):
    """Rows over 72 hours; attack rows have larger IN_BYTES / shorter duration (learnable)."""
    rng = np.random.default_rng(seed)
    lines = [",".join(COLUMNS)]
    for _ in range(rows):
        attack = rng.random() < 0.3
        values = {name: "0" for name in COLUMNS}
        values["FLOW_START_MILLISECONDS"] = str(T0 + int(rng.integers(0, HOURS * 3_600_000)))
        values["FLOW_END_MILLISECONDS"] = values["FLOW_START_MILLISECONDS"]
        values["IPV4_SRC_ADDR"] = "192.0.2.10" if attack else "198.51.100.20"
        values["IPV4_DST_ADDR"] = "203.0.113.5"
        values["PROTOCOL"] = "6"
        values["L7_PROTO"] = "7.178"
        mean = 9.0 + shift if attack else 6.0
        values["IN_BYTES"] = str(int(np.exp(rng.normal(mean, 1.0))))
        values["FLOW_DURATION_MILLISECONDS"] = str(int(rng.exponential(50 if attack else 400)))
        values["SRC_TO_DST_IAT_AVG"] = f"{rng.random():.3f}"
        values["Label"] = "1" if attack else "0"
        values["Attack"] = str(rng.choice(attacks)) if attack else "Benign"
        lines.append(",".join(values[name] for name in COLUMNS))
    lines.append(",".join("x" if n == "Label" else "0" for n in COLUMNS))  # skipped row
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("conf")
    unsw = write_csv(root / "NF-UNSW-NB15-v3.csv", ("Exploits", "DoS", "Generic"), 3000, 1)
    cic = write_csv(root / "NF-CSE-CIC-IDS2018-v3.csv", ("DDoS", "BruteForce"), 3000, 2, 0.5)
    out = root / "prepared"
    prepare(
        {"nf-unsw-nb15-v3": unsw, "nf-cse-cic-ids2018-v3": cic},
        out, train_cap=400, benign_cap=1200, eval_rows=500,
    )  # fmt: skip
    return out


def test_features_exclude_identity_time_and_answer():
    assert len(F.FEATURES) == 47 and len(set(F.FEATURES)) == 47
    for name in ("IPV4_SRC_ADDR", "L4_SRC_PORT", "L4_DST_PORT", "FLOW_START_MILLISECONDS",
                 "Label", "Attack"):  # fmt: skip
        assert name not in F.FEATURES
    assert set(F.FEATURES) | set(F.EXCLUDED) == set(COLUMNS)


def test_split_is_by_block_and_stable():
    assert F.split_of_block("nf-unsw-nb15-v3", 7) == F.split_of_block("nf-unsw-nb15-v3", 7)
    share = [F.split_of_block("nf-unsw-nb15-v3", b) for b in range(5000)]
    assert 0.55 < share.count("train") / 5000 < 0.65
    assert 0.15 < share.count("test") / 5000 < 0.25
    # Two flows in the same hour always share a split.
    hour = (T0 // 3_600_000) * 3_600_000
    assert F.block_of(hour) == F.block_of(hour + 59 * 60_000) != F.block_of(hour + 3_600_000)


def test_class_of():
    assert F.class_of(0, "DoS") == F.BENIGN
    assert F.class_of(1, " DoS ") == "DoS"
    assert F.class_of(1, "") == "unknown-attack"


def test_rates_cap_train_and_keep_eval_ratio():
    counts = {("train", "Generic"): 1000, ("train", "DoS"): 50, ("train", "Benign"): 4000,
              ("test", "Generic"): 300, ("test", "Benign"): 700}  # fmt: skip
    keep = rates(counts, train_cap=100, benign_cap=1000, eval_rows=500)
    assert keep[("train", "Generic")] == 0.1 and keep[("train", "DoS")] == 1.0
    assert keep[("train", "Benign")] == 0.25
    assert keep[("test", "Generic")] == keep[("test", "Benign")] == 0.5


def test_prepare_manifest_counts_and_skips(prepared):
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["features"] == list(F.FEATURES)
    for info in manifest["datasets"].values():
        assert info["skipped"] == {"label_not_0_or_1": 1}
        total = sum(sum(v.values()) for v in info["counts"].values())
        assert total == 3000
        assert sum(info["kept"]["train"].get(c, 0) for c in info["kept"]["train"]) <= 400 * 3 + 1200
    with np.load(prepared / "train.npz") as data:
        assert data["X"].shape[1] == 47 and data["X"].dtype == np.float32


def test_prepare_is_deterministic(prepared, tmp_path):
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    src = prepared.parent
    again = tmp_path / "again"
    prepare(
        {"nf-unsw-nb15-v3": src / "NF-UNSW-NB15-v3.csv",
         "nf-cse-cic-ids2018-v3": src / "NF-CSE-CIC-IDS2018-v3.csv"},
        again, train_cap=400, benign_cap=1200, eval_rows=500,
    )  # fmt: skip
    for split in F.SPLITS:
        with np.load(prepared / f"{split}.npz") as a, np.load(again / f"{split}.npz") as b:
            assert np.array_equal(a["X"], b["X"]) and np.array_equal(a["y"], b["y"])
    assert json.loads((again / "manifest.json").read_text())["datasets"] == manifest["datasets"]


def test_wrong_header_is_refused(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="NetFlow v3 header"):
        prepare_main(["--input", f"nf-unsw-nb15-v3={bad}", "--out", str(tmp_path / "o")])


def test_train_calibrate_and_report(prepared, tmp_path):
    report = run(prepared, tmp_path / "run")
    assert set(report["per_dataset"]) == set(F.DATASETS)
    for entry in report["per_dataset"].values():
        assert entry["role"] == "in-dataset"
        assert entry["calibrated"]["auc"] > 0.9  # the invented signal is easy
        assert 0.0 <= entry["calibrated"]["ece"] <= 1.0
        assert set(entry["pass"]) == {"ece", "auc"}
    assert "macro_in_dataset" in report
    text = (tmp_path / "run" / "report.json").read_text(encoding="utf-8")
    assert "192.0.2" not in text  # counts and measures only

    model = load(tmp_path / "run" / "model.joblib")
    with np.load(prepared / "test.npz") as data:
        p = model.predict(data["X"][:50])
    assert p.shape == (50,) and float(p.min()) >= 0.0 and float(p.max()) <= 1.0


def test_cross_dataset_report(prepared, tmp_path):
    report = run(prepared, tmp_path / "cross", train_datasets=["nf-unsw-nb15-v3"])
    assert report["trained_on"] == ["nf-unsw-nb15-v3"]
    assert report["per_dataset"]["nf-cse-cic-ids2018-v3"]["role"] == "cross-dataset"
    assert "pass" not in report["per_dataset"]["nf-cse-cic-ids2018-v3"]


def test_load_refuses_other_files(tmp_path):
    import joblib

    joblib.dump({"format": "other"}, tmp_path / "x.joblib")
    with pytest.raises(ValueError, match="not an icd-confidence-model-v1"):
        load(tmp_path / "x.joblib")


def test_metrics():
    y = np.array([0, 0, 1, 1])
    perfect = np.array([0.0, 0.0, 1.0, 1.0])
    assert ece(y, perfect) == 0.0
    assert summary(y, perfect)["auc"] == 1.0
    assert ece(np.array([1, 1]), np.array([0.6, 0.6])) == pytest.approx(0.4)
    assert summary(np.array([1, 1]), np.array([0.9, 0.9]))["auc"] is None
    assert sum(b["count"] for b in reliability(y, perfect)) == 4
