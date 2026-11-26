"""Step 6a: stacking, split conformal and clamp on invented probabilities."""

import numpy as np
import pytest

pytest.importorskip("sklearn")

from app.confidence import stack as S  # noqa: E402


def invented(n_groups: int, seed: int, share: float = 0.5):
    """Groups of 10 events; both inputs informative, p_llm one value per group."""
    rng = np.random.default_rng(seed)
    p_clf, p_llm, y, ids = [], [], [], []
    for g in range(n_groups):
        label = int(rng.random() < share)
        llm = 1 / (1 + np.exp(-rng.normal(1.0 if label else -1.0, 1.0)))
        for _ in range(10):
            p_clf.append(1 / (1 + np.exp(-rng.normal(1.5 if label else -1.5, 1.2))))
            p_llm.append(llm)
            y.append(label)
            ids.append(f"s{seed}-g{g}")
    return np.array(p_clf), np.array(p_llm), np.array(y), ids


def test_conformal_threshold_rank():
    scores = np.arange(1, 20) / 20  # 19 scores
    assert S.conformal_threshold(scores, 0.05) == pytest.approx(scores[18])
    assert S.conformal_threshold(np.array([0.1, 0.2]), 0.05) == 1.0  # too few: all possible
    with pytest.raises(ValueError):
        S.conformal_threshold(np.array([]))


def test_fit_uses_both_inputs_and_covers_95_percent():
    p_clf, p_llm, y, ids = invented(600, 1)
    stacker, counts = S.fit(p_clf, p_llm, y, ids, natural_share=0.5)
    assert stacker.b_clf > 0 and stacker.b_llm > 0
    assert counts["fit_events"] + counts["conformal_events"] == len(y)
    report = S.evaluate(stacker, *invented(600, 2)[:3])
    assert 0.93 <= report["conformal_coverage"] <= 0.98
    assert 0 < report["needs_review_share"] < 0.5
    assert report["stacked"]["auc"] > 0.9


def test_groups_never_in_both_halves():
    _, _, _, ids = invented(50, 3)
    halves = {}
    for g in ids:
        halves.setdefault(g, set()).add(S.half_of(g))
    assert all(len(h) == 1 for h in halves.values())


def test_prior_weights_restore_the_natural_share():
    y = np.array([1] * 50 + [0] * 50)
    w = S.prior_weights(y, 0.2)
    assert (w * y).sum() / w.sum() == pytest.approx(0.2)
    assert (S.prior_weights(y, None) == 1).all()


def test_natural_prior_lowers_c():
    p_clf, p_llm, y, ids = invented(600, 4)
    balanced, _ = S.fit(p_clf, p_llm, y, ids, natural_share=0.5)
    rare, _ = S.fit(p_clf, p_llm, y, ids, natural_share=0.1)
    assert rare.a < balanced.a


def test_combine_clamps_and_flags():
    stacker = S.Stacker(a=0.0, b_clf=1.0, b_llm=1.0, threshold=0.6)
    low = S.combine(0.001, 0.001, stacker)
    assert low.c == S.C_MIN and low.flags == ()
    mid = S.combine(0.5, 0.5, stacker)
    assert mid.c == pytest.approx(0.5) and mid.flags == ("needs_review",)
    pending = S.combine(0.8, None, stacker)
    assert (pending.c, pending.flags) == (0.8, ("llm_pending",))
    down = S.combine(0.01, None, None, llm_flag="llm_unavailable")
    assert (down.c, down.flags) == (S.C_MIN, ("llm_unavailable",))


def test_save_and_load(tmp_path):
    stacker = S.Stacker(0.1, 0.9, 0.4, 0.7, meta={"classifier": "x"})
    S.save(stacker, tmp_path / "stacker.json")
    again = S.load(tmp_path / "stacker.json")
    assert (again.a, again.b_clf, again.b_llm, again.threshold) == (0.1, 0.9, 0.4, 0.7)
    assert again.meta == {"classifier": "x"}
    (tmp_path / "bad.json").write_text('{"format": "other"}')
    with pytest.raises(ValueError):
        S.load(tmp_path / "bad.json")


def test_stack_fit_end_to_end(tmp_path):
    pytest.importorskip("pyarrow")
    import json

    from app.confidence import groups as G
    from app.confidence import llm_calibrate as LC
    from app.confidence import llm_opinion as LO
    from app.confidence.prepare import prepare
    from app.confidence.stack_fit import main
    from app.confidence.train import run
    from tests.confidence.test_llm_confidence import client, write_csv

    csv = write_csv(tmp_path / "NF-UNSW-NB15-v3.csv", rows=12000)
    prepare({"nf-unsw-nb15-v3": csv}, tmp_path / "prepared", train_cap=2000, benign_cap=4000,
            eval_rows=4000)  # fmt: skip
    run(tmp_path / "prepared", tmp_path / "clf")
    files = {}
    for split in ("calibration", "test"):
        groups = tmp_path / f"groups-{split}.jsonl"
        G.main(["--input", f"nf-unsw-nb15-v3={csv}", "--split", split, "--out", str(groups),
                "--groups-per-class", "40"])  # fmt: skip
        opinions = tmp_path / f"opinions-{split}.jsonl"
        LO.run(groups, opinions, client(), workers=2)
        files[split] = (groups, opinions)
    LC.run(files["calibration"], files["test"], tmp_path / "llm")
    model = tmp_path / "clf" / "model.joblib"
    assert main(["--out", str(tmp_path / "stack"), "--model", str(model),
                 "--llm-calibrator", str(tmp_path / "llm" / "llm_calibrator.json"),
                 "--calibration", *map(str, files["calibration"]),
                 "--test", *map(str, files["test"]),
                 "--input", f"nf-unsw-nb15-v3={csv}"]) == 0  # fmt: skip
    report = json.loads((tmp_path / "stack" / "stack_report.json").read_text())
    pooled = report["test"]["pooled"]
    assert pooled["stacked"]["rows"] > 0 and pooled["conformal_coverage"] > 0.85
    stacker = S.load(tmp_path / "stack" / "stacker.json")
    assert stacker.meta["llm_calibrator"]["prompt_version"] == LO.PROMPT_VERSION
    assert "192.0.2" not in (tmp_path / "stack" / "stack_report.json").read_text()
