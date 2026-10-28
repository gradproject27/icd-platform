import importlib.util
import json
from pathlib import Path

BENCH = Path(__file__).resolve().parents[3] / "tools" / "ai1" / "bench.py"


def _load_bench():
    spec = importlib.util.spec_from_file_location("ai1_bench", BENCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stub_run_writes_a_valid_record(tmp_path):
    bench = _load_bench()
    assert bench.main(["--backend", "stub", "--runs", "2", "--out", str(tmp_path)]) == 0
    record = json.loads((tmp_path / "model_run_record.json").read_text(encoding="utf-8"))
    assert record["load"]["ok"] is True
    assert [r["valid_analysis"] for r in record["runs"]] == [True, True]
    assert [r["flagged_coverage"] for r in record["runs"]] == [1.0, 1.0]
    assert record["model"]["prompt_version"] == "ai1-prompt-v0"
    text = (tmp_path / "model_run_record.md").read_text(encoding="utf-8")
    assert "| Valid analyses (parse + grounding + contract) | 2 of 2 |" in text


def test_openai_http_sends_the_schema_and_warms_up(monkeypatch):
    bench = _load_bench()
    args = bench.argparse.Namespace(
        endpoint="http://x", model="m", revision=None, warmup=True, json_schema=True
    )
    backend = bench.OpenAIHTTP(args)
    sent = []
    reply = {"choices": [{"message": {"content": "{}"}}], "usage": {"completion_tokens": 3}}
    monkeypatch.setattr(backend, "_post", lambda body: sent.append(body) or reply)
    backend.load()
    text, usage = backend.generate([{"role": "user", "content": "hi"}], 10, 0.0)
    assert sent[0]["max_tokens"] == 1
    schema = sent[1]["response_format"]["json_schema"]["schema"]
    assert schema == bench.LlmOutput.model_json_schema()
    assert (text, usage["completion_tokens"]) == ("{}", 3)


def test_unreachable_endpoint_is_recorded_not_raised(tmp_path):
    bench = _load_bench()
    args = ["--backend", "openai_http", "--endpoint", "http://127.0.0.1:9/v1/chat/completions"]
    assert bench.main([*args, "--runs", "1", "--out", str(tmp_path)]) == 1
    record = json.loads((tmp_path / "model_run_record.json").read_text(encoding="utf-8"))
    assert record["errors"] and "error" in record["runs"][0]
