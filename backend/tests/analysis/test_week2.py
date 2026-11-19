"""AI1 Week 2: the five test incidents, the HPC handoff files, the C5 fields and the metrics."""

import copy
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.analysis import ReportMeta, run_analysis
from app.analysis.export import SCHEMA_DIR, SCHEMAS
from app.analysis.handoff import HPC_OUTPUT_FORMAT, HpcOutput, analyze_hpc_output
from app.analysis.incident_fields import apply_result
from app.analysis.metrics import ExpectedIncident, score_run, summarize
from app.contracts import AnalysisStatus, Event, EventRole, EvidencePackage
from app.contracts.export import schema_text
from app.correlation import correlate, load_config, score_incidents
from app.response.freeze import report_valid

ROOT = Path(__file__).resolve().parents[3]
AI1 = ROOT / "fixtures" / "ai1"
TOOLS = ROOT / "tools" / "ai1"
NOW = datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
EXPECTED = [
    ExpectedIncident.model_validate(e)
    for e in json.loads((AI1 / "expected.json").read_text(encoding="utf-8"))
]
NAMES = [Path(e.package).stem for e in EXPECTED]


def _tool(name: str):
    spec = importlib.util.spec_from_file_location(f"ai1_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package(name: str) -> EvidencePackage:
    return EvidencePackage.model_validate_json((AI1 / "packages" / f"{name}.json").read_text())


def _reference(name: str) -> str:
    return (AI1 / "reference" / f"{name}.json").read_text(encoding="utf-8")


def _meta(report_id: str = "rep-test") -> ReportMeta:
    return ReportMeta(report_id=report_id, generated_at=NOW, generated_by="local", model_id="m")


def test_committed_packages_are_what_the_builder_makes_now():
    built = _tool("make_packages").build()
    assert sorted(built) == sorted(f"{n}.json" for n in NAMES)
    for name, text in built.items():
        committed = (AI1 / "packages" / name).read_text(encoding="utf-8")
        assert committed == text, f"{name} is stale: run python tools/ai1/make_packages.py"


@pytest.mark.parametrize("expected", EXPECTED, ids=NAMES)
def test_expectations_match_their_package(expected):
    package = _package(Path(expected.package).stem)
    assert package.masked
    assert package.incident_id == expected.incident_id
    flagged = [e.event_id for e in package.events if e.role == EventRole.FLAGGED]
    assert expected.must_cite == flagged


@pytest.mark.parametrize("expected", EXPECTED, ids=NAMES)
def test_reference_answer_meets_every_expectation(expected):
    name = Path(expected.package).stem
    evidence = _package(name)
    result = run_analysis(_reference(name), evidence, _meta())
    assert result.valid, result.problems()
    assert result.grounding.ungrounded == ()
    score = score_run(name, 1, result, evidence, expected)
    assert score.coverage == 1.0
    assert score.outcome_match and score.attack_type_match and score.freeze_match


def test_only_the_high_incident_would_freeze():
    frozen = []
    for expected in EXPECTED:
        name = Path(expected.package).stem
        evidence = _package(name)
        result = run_analysis(_reference(name), evidence, _meta())
        frozen.append(score_run(name, 1, result, evidence, expected).would_freeze)
    assert frozen == [e.freeze_expected for e in EXPECTED] == [True, False, False, False, False]


@pytest.mark.parametrize("name", list(SCHEMAS))
def test_committed_ai1_schemas_are_current(name):
    committed = (SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8")
    assert committed == schema_text(SCHEMAS[name]), "run python -m app.analysis.export"


def _hpc_output(name: str, **changes) -> HpcOutput:
    evidence = _package(name)
    data = {
        "format": HPC_OUTPUT_FORMAT,
        "package_id": evidence.package_id,
        "incident_id": evidence.incident_id,
        "generated_by": "hpc",
        "model_id": "Qwen/Qwen3-8B@0123abc",
        "prompt_version": "ai1-prompt-v0",
        "raw_output": _reference(name),
        "started_at": "2026-01-15T23:00:00Z",
        "finished_at": "2026-01-15T23:00:40Z",
    }
    data.update(changes)
    return HpcOutput.model_validate(data)


def test_hpc_output_round_trip_and_analysis():
    output = _hpc_output("a-multistep-high")
    assert HpcOutput.model_validate_json(output.model_dump_json()) == output
    result = analyze_hpc_output(output, _package("a-multistep-high"), "rep-a")
    assert result.valid
    assert result.report.generated_by == "hpc"
    assert result.report.model_id == "Qwen/Qwen3-8B@0123abc"
    assert result.report.generated_at == output.finished_at


@pytest.mark.parametrize(
    "changes",
    [{"raw_output": None}, {"error": "CUDA out of memory"}, {"format": "icd-hpc-output-v2"}],
    ids=["neither", "both", "format"],
)
def test_hpc_output_rejects_bad_files(changes):
    with pytest.raises(ValueError):
        _hpc_output("c1-fuzzers-low", **changes)


def test_run_error_and_wrong_package_are_failed_analyses():
    failed = _hpc_output("c1-fuzzers-low", raw_output=None, error="CUDA out of memory")
    result = analyze_hpc_output(failed, _package("c1-fuzzers-low"), "rep-x")
    assert not result.valid and [p.check for p in result.problems()] == ["H2"]
    other = analyze_hpc_output(_hpc_output("c1-fuzzers-low"), _package("c2-dos-medium"), "rep-x")
    assert not other.valid and [p.check for p in other.problems()] == ["H1"]


def test_runner_writes_an_output_file_the_app_host_accepts(tmp_path):
    out = tmp_path / "out.json"
    evidence = AI1 / "packages" / "c2-dos-medium.json"
    args = ["--evidence", str(evidence), "--output", str(out), "--backend", "stub"]
    assert _tool("icd_analyze").main([*args, "--site", "local"]) == 0
    output = HpcOutput.model_validate_json(out.read_text(encoding="utf-8"))
    assert output.generated_by == "local" and output.prompt_version == "ai1-prompt-v1"
    assert analyze_hpc_output(output, _package("c2-dos-medium"), "rep-c2").valid


def test_runner_refuses_an_unmasked_package(tmp_path):
    data = json.loads((AI1 / "packages" / "c2-dos-medium.json").read_text(encoding="utf-8"))
    data["masked"] = False
    evidence = tmp_path / "unmasked.json"
    evidence.write_text(json.dumps(data), encoding="utf-8")
    args = ["--evidence", str(evidence), "--output", str(tmp_path / "o.json"), "--backend", "stub"]
    assert _tool("icd_analyze").main(args) == 2
    assert not (tmp_path / "o.json").exists()


def _incident_a():
    events = [
        Event.model_validate(e)
        for e in json.loads((ROOT / "fixtures/correlation/events.json").read_text("utf-8"))
    ]
    config = load_config()
    incidents = score_incidents(
        correlate(events, config, NOW).incidents, events, NOW, correlation=config
    )
    return next(i for i in incidents if i.events[0].event_id == "fx-002")


def test_valid_analysis_sets_the_fields_c5_reads():
    incident = _incident_a()
    result = run_analysis(_reference("a-multistep-high"), _package("a-multistep-high"), _meta())
    updated = apply_result(incident, result, NOW)
    assert updated.analysis_status == AnalysisStatus.SUCCEEDED
    assert updated.latest_report_id == "rep-test"
    assert updated.confidence == result.report.confidence >= 0.75
    assert updated.analysis_attempts == incident.analysis_attempts + 1
    assert report_valid(updated)


def test_failed_analysis_clears_confidence_and_is_not_valid():
    incident = _incident_a()
    good = run_analysis(_reference("a-multistep-high"), _package("a-multistep-high"), _meta())
    succeeded = apply_result(incident, good, NOW)
    bad = run_analysis("not json", _package("a-multistep-high"), _meta("rep-2"))
    failed = apply_result(succeeded, bad, NOW)
    assert failed.analysis_status == AnalysisStatus.FAILED
    assert failed.confidence is None
    assert failed.analysis_attempts == 2
    assert not report_valid(failed)


def test_a_run_with_only_hypotheses_is_left_out_of_the_grounding_rate():
    expected = EXPECTED[-1]
    evidence = _package("f-no-entities")
    answer = json.loads(_reference("f-no-entities"))
    answer["summary"]["category"] = "hypothesis"
    answer["risk_justification"]["category"] = "hypothesis"
    result = run_analysis(json.dumps(answer), evidence, _meta())
    assert result.valid and result.grounding.factual_claims == 0
    score = score_run("f-no-entities", 1, result, evidence, expected)
    assert score.grounding_rate is None
    reference = run_analysis(_reference("a-multistep-high"), _package("a-multistep-high"), _meta())
    full = score_run("a-multistep-high", 1, reference, _package("a-multistep-high"), EXPECTED[0])
    metrics = {m.key: m for m in summarize([full, score])}
    assert metrics["E4"].value == 1.0


def test_metrics_catch_an_invented_host_and_lost_coverage():
    expected = EXPECTED[0]
    evidence = _package("a-multistep-high")
    broken = json.loads(_reference("a-multistep-high"))
    bad = copy.deepcopy(broken)
    bad["summary"]["text"] += " host-09 was also reached."
    thin = copy.deepcopy(broken)
    thin["sequence"], thin["findings"], thin["weaknesses"] = thin["sequence"][:1], [], None
    thin["summary"]["cited_event_ids"] = ["fx-002"]
    thin["summary"]["entities"] = {"hosts": ["host-01"], "ips": ["ip-01"], "users": []}
    thin["summary"]["text"] = "ip-01 scanned host-01."
    thin["impact"] = None
    thin["recommendations"] = []
    thin["risk_justification"] = None
    thin["attack_type"]["claim"]["cited_event_ids"] = ["fx-002"]
    scores = []
    for run, answer in enumerate([bad, thin], start=1):
        result = run_analysis(json.dumps(answer), evidence, _meta())
        scores.append(score_run("a-multistep-high", run, result, evidence, expected))
    assert scores[0].invented == 1 and not scores[0].valid and not scores[0].freeze_match
    assert scores[1].valid and scores[1].coverage == 0.25
    metrics = {m.key: m for m in summarize(scores)}
    assert metrics["E1"].value == 0.5 and metrics["E1"].passed is False
    assert metrics["E2"].passed is False
    assert metrics["E5"].passed is False
    assert metrics["E11"].passed is None


def test_evaluate_scores_a_stub_run(tmp_path):
    packages = sorted(str(p) for p in (AI1 / "packages").glob("*.json"))
    bench_args = ["--backend", "stub", "--packages", *packages, "--runs", "1", "--out"]
    assert _tool("bench").main([*bench_args, str(tmp_path)]) == 0
    assert _tool("evaluate").main([str(tmp_path)]) == 0
    data = json.loads((tmp_path / "evaluation.json").read_text(encoding="utf-8"))
    assert all(m["passed"] in (True, None) for m in data["metrics"])
    assert len(list((tmp_path / "reports").glob("*.json"))) == 5
    assert "| E1 | Valid analyses | 1.0 |" in (tmp_path / "evaluation.md").read_text("utf-8")


def test_runner_records_its_settings_for_the_model_service(tmp_path):
    out = tmp_path / "out.json"
    evidence = AI1 / "packages" / "c1-fuzzers-low.json"
    args = ["--evidence", str(evidence), "--output", str(out), "--backend", "stub", "--no-thinking"]
    assert _tool("icd_analyze").main(args) == 0
    output = HpcOutput.model_validate_json(out.read_text(encoding="utf-8"))
    assert output.settings["no_thinking"] is True
    assert output.settings["max_new_tokens"] == 4900
