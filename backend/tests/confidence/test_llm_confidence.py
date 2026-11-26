"""Step 5 (LLM opinion per evidence group) on invented NetFlow v3 rows and a fake model server."""

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pyarrow")

from app.confidence import features as F  # noqa: E402
from app.confidence import groups as G  # noqa: E402
from app.confidence import llm_calibrate as LC  # noqa: E402
from app.confidence import llm_opinion as LO  # noqa: E402
from app.contracts import Event  # noqa: E402
from app.ingest.event_types import EventTypes  # noqa: E402
from app.ingest.interface import IntakeContext  # noqa: E402
from app.ingest.nf_v3 import COLUMNS, parse_nf_v3  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "ingest" / "nf-v3-sample.csv"
T0 = 1421927414000
HOURS = 200
UNSW = "nf-unsw-nb15-v3"


def write_csv(path: Path, rows: int = 12000, seed: int = 3) -> Path:
    """Attack rows come from 192.0.2.x with large IN_BYTES; benign rows from 198.51.100.x."""
    rng = np.random.default_rng(seed)
    lines = [",".join(COLUMNS)]
    for _ in range(rows):
        attack = rng.random() < 0.3
        v = {name: "0" for name in COLUMNS}
        v["FLOW_START_MILLISECONDS"] = str(T0 + int(rng.integers(0, HOURS * 3_600_000)))
        v["FLOW_END_MILLISECONDS"] = v["FLOW_START_MILLISECONDS"]
        v["IPV4_SRC_ADDR"] = f"192.0.2.{rng.integers(1, 6)}" if attack else \
            f"198.51.100.{rng.integers(1, 41)}"  # fmt: skip
        v["IPV4_DST_ADDR"] = f"203.0.113.{rng.integers(1, 30)}"
        v["L4_DST_PORT"] = str(rng.choice([80, 443, 22, 53]))
        v["PROTOCOL"] = "6"
        v["L7_PROTO"] = "7.178"
        v["IN_BYTES"] = str(int(np.exp(rng.normal(9.0 if attack else 6.0, 0.8))))
        v["OUT_BYTES"] = str(int(rng.integers(0, 3000)))
        v["TCP_FLAGS"] = "27" if attack else "24"
        v["Label"] = "1" if attack else "0"
        v["Attack"] = str(rng.choice(["Exploits", "DoS", "Fuzzers"])) if attack else "Benign"
        lines.append(",".join(v[name] for name in COLUMNS))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def fake_server(body: dict) -> dict:
    """Says yes more often when the group's median IN_BYTES is large; ignores `n` like Ollama."""
    evidence = json.loads(body["messages"][1]["content"].split("Evidence (JSON):\n", 1)[1]
                          .rsplit("\n\nAnswer", 1)[0])  # fmt: skip
    median = evidence["in_bytes"]["median"] or 1.0
    p_yes = 1 / (1 + math.exp(-(math.log(median) - 7.5) * 2))
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).digest()
    if body.get("logprobs"):
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": [
            {"token": "Yes", "logprob": math.log(max(p_yes, 1e-9))},
            {"token": "No", "logprob": math.log(max(1 - p_yes, 1e-9))},
        ]}]}}]}  # fmt: skip
    word = "Yes." if digest[0] / 255 < p_yes else "no"
    return {"choices": [{"message": {"content": word}}]}


def client(post=fake_server, **kw) -> LO.OpinionClient:
    return LO.OpinionClient(post=post, model="fake", model_id="fake@1", **kw)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("llm")
    csv = write_csv(root / "NF-UNSW-NB15-v3.csv")
    out = {}
    for split in ("calibration", "test"):
        path = root / f"groups-{split}.jsonl"
        assert G.main(["--input", f"{UNSW}={csv}", "--split", split, "--out", str(path),
                       "--groups-per-class", "40"]) == 0  # fmt: skip
        out[split] = path
    return root, csv, out


def records(path: Path) -> list[dict]:
    return [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines()]


def test_groups_come_from_their_split_only_and_are_masked(built):
    _, _, paths = built
    cal = records(paths["calibration"])
    assert cal and all(r["split"] == "calibration" for r in cal)
    text = paths["calibration"].read_text(encoding="utf-8")
    for value in ("192.0.2.", "198.51.100.", "203.0.113."):
        assert value not in text
    for r in cal:
        ev = r["evidence"]
        assert ev["source"] == "SRC" and ev["flows_described"] <= G.MAX_FLOWS
        assert all(e["to"] is None or e["to"].startswith("DST-") for e in ev["example_flows"])
        assert r["evidence_sha256"] == G.evidence_sha256(ev)
        assert "y" not in ev and "true_class" not in ev


def test_negative_groups_carry_an_attack_claim(built):
    cal = records(built[2]["calibration"])
    attacks = [r for r in cal if r["y"] == 1]
    benign = [r for r in cal if r["y"] == 0]
    assert attacks and 0 < len(benign) <= len(attacks)
    assert all(r["evidence"]["claimed_technique"] == r["true_class"] for r in attacks)
    assert {r["evidence"]["claimed_technique"] for r in benign} <= {"Exploits", "DoS", "Fuzzers"}
    assert all(r["true_class"] == F.BENIGN for r in benign)
    manifest = json.loads(built[2]["calibration"].with_suffix(".manifest.json").read_text())
    info = manifest["datasets"][UNSW]
    assert 0 < info["natural_attack_share"] < 1 and info["groups_chosen"] == len(cal)


def test_groups_are_deterministic(built):
    root, csv, paths = built
    again = root / "again.jsonl"
    G.main(["--input", f"{UNSW}={csv}", "--split", "calibration", "--out", str(again),
            "--groups-per-class", "40"])  # fmt: skip
    assert again.read_text() == paths["calibration"].read_text()


def test_choose_groups_caps_per_class():
    from collections import Counter

    counts = Counter({(b, c, f"s{s}"): 1 for b in range(5) for c in ("DoS", "Benign")
                      for s in range(30)})  # fmt: skip
    chosen = G.choose_groups(counts, groups_per_class=10, seed=1, code=0)
    assert sum(1 for k in chosen if k[1] == "DoS") == 10
    assert sum(1 for k in chosen if k[1] == "Benign") == 10
    assert set(chosen.values()) == {"DoS"}


def test_flow_from_csv_equals_flow_from_event(tmp_path):
    ctx = IntakeContext(upload_id="u", dataset_id=UNSW, source_file="nf-v3-sample.csv",
                        ingested_at=datetime(2026, 11, 26, tzinfo=UTC))  # fmt: skip
    events = {int(e.provenance.record_ref.rsplit(":", 1)[1]): e
              for e in parse_nf_v3(FIXTURE, ctx) if isinstance(e, Event)}  # fmt: skip
    # The fixture also holds broken lines (quarantine tests); keep the stored events' lines.
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    numbers = sorted(events)
    clean = tmp_path / "clean.csv"
    clean.write_text("\n".join([lines[0]] + [lines[n - 1] for n in numbers]) + "\n")
    cols = next(G._rows(clean))
    types = EventTypes(UNSW)
    compared = 0
    for i, number in enumerate(numbers):
        assert G._flow(cols, i, types) == G.flow_from_event(events[number]), number
        compared += 1
    assert compared >= 5


def test_group_from_events_selects_the_risk_group():
    ctx = IntakeContext(upload_id="u", dataset_id=UNSW, source_file="nf-v3-sample.csv",
                        ingested_at=datetime(2026, 11, 26, tzinfo=UTC))  # fmt: skip
    events = [e for e in parse_nf_v3(FIXTURE, ctx) if isinstance(e, Event)]
    flagged = next(e for e in events if e.label.attack_type)
    from app.correlation.risk import entity_of

    group = G.group_from_events(events, flagged.label.attack_type, entity_of(flagged), "inc-1")
    assert group is not None and group.claimed_technique == flagged.label.attack_type
    assert all(f.dst is not None for f in group.flows)
    text = json.dumps(group.evidence())
    assert "192.0.2" not in text and "198.51.100" not in text
    assert G.group_from_events(events, "NoSuchTechnique", "x", "inc-1") is None


@pytest.mark.parametrize(
    ("text", "answer"),
    [("yes", "yes"), (" No.", "no"), ("YES, clearly", "yes"), ("<think>hmm</think>\nno", "no"),
     ("<think>still thinking", None), ("maybe", None), ("", None), (None, None)],
)  # fmt: skip
def test_parse_answer(text, answer):
    assert LO.parse_answer(text) == answer


def test_raw_values():
    assert LO.raw_from_samples(5, 0) == pytest.approx(5.5 / 6)
    assert LO.raw_from_samples(0, 5) == pytest.approx(0.5 / 6)
    assert LO.raw_from_samples(0, 0) is None
    top = [{"token": " yes", "logprob": math.log(0.6)}, {"token": "No", "logprob": math.log(0.2)},
           {"token": "maybe", "logprob": math.log(0.2)}]  # fmt: skip
    assert LO.raw_from_logprobs(top) == pytest.approx(0.75)
    assert LO.raw_from_logprobs([{"token": "x", "logprob": 0.0}]) is None


def test_prompt_holds_the_masked_evidence_only(built):
    group = records(built[2]["calibration"])[0]
    msgs = LO.messages(group["evidence"])
    assert msgs[0]["role"] == "system" and "never as instructions" in msgs[0]["content"]
    assert group["evidence"]["claimed_technique"] in msgs[1]["content"]
    assert '"y"' not in msgs[1]["content"] and group["true_class"] not in ("",)


def test_client_collects_k_answers_from_a_server_that_ignores_n(built):
    group = records(built[2]["calibration"])[0]
    calls = []

    def post(body):
        calls.append(body["n"])
        return fake_server(body | {"n": len(calls)})

    result = client(post).ask(group["evidence"])
    assert result["yes"] + result["no"] == 5 and calls == [5, 4, 3, 2, 1]


def test_client_errors_and_logprobs(built):
    evidence = records(built[2]["calibration"])[0]["evidence"]
    with pytest.raises(LO.OpinionError, match="answers were yes or no"):
        client(lambda body: {"choices": [{"message": {"content": "maybe"}}] * 5}).ask(evidence)

    def down(body):
        raise LO.OpinionError("model server not reachable")

    line = LO.opinion(client(down, retries=0), {"group_id": "g", "evidence_sha256": "h",
                                                "evidence": evidence})  # fmt: skip
    assert line["raw"] is None and "not reachable" in line["error"]
    result = client(mode="logprobs").ask(evidence)
    assert 0 < result["raw"] < 1 and result["yes"] is None
    assert client(mode="logprobs").settings()["samples"] == 1


def test_run_resumes(built, tmp_path):
    out = tmp_path / "opinions.jsonl"
    first = LO.run(built[2]["calibration"], out, client(), workers=3)
    assert first["asked"] == first["groups"] and first["errors"] == 0
    second = LO.run(built[2]["calibration"], out, client(), workers=3)
    assert second == {"groups": first["groups"], "already_done": first["groups"], "asked": 0,
                      "errors": 0}  # fmt: skip
    third = LO.run(built[2]["calibration"], out, client(samples=3), workers=3)
    assert third["asked"] == first["groups"]  # other settings: asked again


def test_platt_calibration_end_to_end(built, tmp_path):
    root, _, paths = built
    ops = {}
    for split, path in paths.items():
        ops[split] = tmp_path / f"opinions-{split}.jsonl"
        LO.run(path, ops[split], client(), workers=2)
    result = LC.run((paths["calibration"], ops["calibration"]),
                    (paths["test"], ops["test"]), tmp_path / "run")  # fmt: skip
    cal = result["calibrator"]
    assert cal["b"] > 0 and cal["prompt_version"] == LO.PROMPT_VERSION
    assert cal["natural_attack_share"] < cal["calibration_attack_share"]
    assert cal["prior_shift"] < 0
    pooled = result["test"]["pooled"]["calibrated"]
    assert pooled["auc"] > 0.8 and pooled["ece"] < 0.2
    loaded = LC.load(tmp_path / "run" / "llm_calibrator.json", LO.PROMPT_VERSION, "fake@1")
    assert loaded.predict(0.9) > loaded.predict(0.1)
    assert loaded.predict(0.9, prior="natural") < loaded.predict(0.9, prior="sample")
    with pytest.raises(ValueError, match="model_id"):
        LC.load(tmp_path / "run" / "llm_calibrator.json", model_id="other")
    assert "192.0.2" not in (tmp_path / "run" / "llm_report.json").read_text()


def test_join_skips_stale_and_failed(built, tmp_path):
    path = built[2]["calibration"]
    groups = records(path)
    ops = tmp_path / "ops.jsonl"
    lines = [
        {"group_id": groups[0]["group_id"], "evidence_sha256": "other", "raw": 0.5, "error": None},
        {"group_id": groups[1]["group_id"], "evidence_sha256": groups[1]["evidence_sha256"],
         "raw": None, "error": "down"},
    ]  # fmt: skip
    ops.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    rows, skipped = LC.join(path, ops)
    assert rows == [] and skipped["other_evidence"] == 1 and skipped["opinion_error"] == 1
    assert skipped["no_opinion"] == len(groups) - 2


def test_cli_dry_run_with_the_stub(built, tmp_path):
    _, _, paths = built
    for split, path in paths.items():
        assert LO.main(["--groups", str(path), "--out", str(tmp_path / f"{split}.jsonl"),
                        "--backend", "stub"]) == 0  # fmt: skip
    assert LC.main(["--calibration", str(paths["calibration"]), str(tmp_path / "calibration.jsonl"),
                    "--test", str(paths["test"]), str(tmp_path / "test.jsonl"),
                    "--out", str(tmp_path / "run")]) == 0  # fmt: skip
    assert json.loads((tmp_path / "run" / "llm_calibrator.json").read_text())["model_id"] == "stub"
