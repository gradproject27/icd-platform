"""risk-v1 step 6b: the cluster side of the confidence handoff, on invented rows and models."""

import json

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pyarrow")

from app.confidence import batch_run  # noqa: E402
from app.confidence import features as F  # noqa: E402
from app.confidence import groups as G  # noqa: E402
from app.confidence import llm_calibrate as LC  # noqa: E402
from app.confidence import llm_opinion as LO  # noqa: E402
from app.confidence.handoff import (  # noqa: E402
    INPUT_FORMAT,
    ConfidenceOutput,
    EventValue,
    to_confidences,
)
from app.confidence.prepare import prepare  # noqa: E402
from app.confidence.stack_fit import main as stack_main  # noqa: E402
from app.confidence.train import run as train  # noqa: E402
from tests.confidence.test_llm_confidence import client, write_csv  # noqa: E402


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    root = tmp_path_factory.mktemp("batch")
    csv = write_csv(root / "NF-UNSW-NB15-v3.csv", rows=12000)
    prepare({"nf-unsw-nb15-v3": csv}, root / "prepared", train_cap=2000, benign_cap=4000,
            eval_rows=4000)  # fmt: skip
    train(root / "prepared", root / "clf")
    files = {}
    for split in ("calibration", "test"):
        groups, opinions = root / f"groups-{split}.jsonl", root / f"opinions-{split}.jsonl"
        G.main(["--input", f"nf-unsw-nb15-v3={csv}", "--split", split, "--out", str(groups),
                "--groups-per-class", "40"])  # fmt: skip
        LO.run(groups, opinions, client(), workers=2)
        files[split] = (groups, opinions)
    LC.run(files["calibration"], files["test"], root / "llm")
    stack_main(["--out", str(root / "stack"), "--model", str(root / "clf" / "model.joblib"),
                "--llm-calibrator", str(root / "llm" / "llm_calibrator.json"),
                "--calibration", *map(str, files["calibration"]),
                "--test", *map(str, files["test"]),
                "--input", f"nf-unsw-nb15-v3={csv}"])  # fmt: skip
    group = json.loads(files["test"][0].read_text().splitlines()[0])
    rng = np.random.default_rng(5)
    events = [{"event_id": f"e{i}", "features": [float(v) for v in rng.random(len(F.FEATURES))]}
              for i in range(4)]  # fmt: skip
    data = {"format": INPUT_FORMAT, "request_id": "job-1", "feature_set": F.FEATURE_SET_VERSION,
            "features": list(F.FEATURES), "events": events,
            "groups": [{**group, "event_ids": ["e0", "e1"]}]}  # fmt: skip
    return root, data


def paths(root):
    return (root / "clf" / "model.joblib", root / "llm" / "llm_calibrator.json",
            root / "stack" / "stacker.json")  # fmt: skip


def test_every_event_gets_c_and_the_versions(models):
    root, data = models
    out = batch_run.run(data, *paths(root), client())
    assert out.error is None and set(out.events) == {"e0", "e1", "e2", "e3"}
    assert all(0.05 <= v.c <= 1 for v in out.events.values())
    assert out.events["e0"].p_llm is not None and out.events["e2"].p_llm is None
    assert "llm_unavailable" in out.events["e2"].flags  # no group opinion for e2
    assert out.versions["llm_model"] == "fake@1" and out.version.startswith("clf-")
    final = to_confidences(out)
    assert final.phase == "final" and final.values["e0"].p_clf == out.events["e0"].p_clf


def test_a_failed_llm_opinion_falls_back_to_p_clf(models):
    root, data = models

    def down(body):
        raise LO.OpinionError("model server not reachable")

    out = batch_run.run(data, *paths(root), client(down, retries=0))
    assert all(v.p_llm is None and "llm_unavailable" in v.flags for v in out.events.values())


def test_a_calibrator_of_another_model_is_refused(models):
    root, data = models
    other = LO.OpinionClient(post=lambda b: {}, model="x", model_id="other@2")
    with pytest.raises(ValueError, match="model_id"):
        batch_run.run(data, *paths(root), other)


def test_cli_writes_an_error_output_instead_of_values(models, tmp_path):
    root, data = models
    bad = tmp_path / "in.json"
    bad.write_text(json.dumps({**data, "features": ["x"]}))
    out = tmp_path / "out.json"
    model, cal, stack = paths(root)
    code = batch_run.main(["--input", str(bad), "--output", str(out), "--model", str(model),
                           "--llm-calibrator", str(cal), "--stacker", str(stack),
                           "--endpoint", "http://127.0.0.1:9/v1",
                           "--llm-model", "fake"])  # fmt: skip
    result = ConfidenceOutput.model_validate_json(out.read_text())
    assert code == 1 and result.error and result.request_id == "job-1" and not result.events


def test_cluster_values_are_clamped_and_flags_filtered():
    out = ConfidenceOutput(request_id="r", version="v", events={
        "a": EventValue(c=0.0, p_clf=0.0, flags=["needs_review", "rm -rf"])})  # fmt: skip
    value = to_confidences(out).values["a"]
    assert value.c == 0.05 and value.flags == ("needs_review",)
    with pytest.raises(ValueError):
        to_confidences(ConfidenceOutput(request_id="r", error="boom"))
