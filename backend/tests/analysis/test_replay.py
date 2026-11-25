"""Replay backend (task 31): recorded real-model answers match across uploads and pass the same
checks as a live answer; failures replay as failures; a missing or mixed recording is refused
and never filled by the stub."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.analysis.backends import BackendError, Generation, generator_from_env
from app.analysis.replay import (
    INCIDENT_PLACEHOLDER,
    MODEL_PREFIX,
    Recording,
    ReplayGenerator,
    default_files,
    load_recordings,
    main,
    platform_packages,
    record_file,
    replay_key,
)
from app.analysis.service import analyze_package
from app.analysis.stub import StubGenerator

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "correlation" / "events.json"
UNSW_SAMPLE = ROOT / "fixtures" / "ingest" / "unsw-nb15-sample.csv"
NOW = datetime(2026, 11, 25, tzinfo=UTC)


class FakeClusterModel(StubGenerator):
    """Stands in for the 27B model: the stub's text, recorded as an hpc run."""

    generated_by, model_id = "hpc", "fake-27b"


class Babbling:
    generated_by, model_id = "hpc", "fake-27b"

    def generate(self, messages, evidence) -> Generation:
        return Generation(f"I think {evidence.incident_id} is fine.")


class Silent:
    generated_by, model_id = "hpc", "fake-27b"

    def generate(self, messages, evidence) -> Generation:
        raise BackendError("timeout")


def record(generator=None, dataset="fixture", path=FIXTURE) -> Recording:
    return record_file(dataset, path, generator or FakeClusterModel(), lambda: NOW)


def test_key_ignores_the_upload_but_not_the_evidence():
    first = platform_packages("fixture", FIXTURE, NOW, scope="upl-a")
    second = platform_packages("fixture", FIXTURE, datetime(2027, 1, 1, tzinfo=UTC), "upl-b")
    assert [p.incident_id for p in first] != [p.incident_id for p in second]
    assert [replay_key(p) for p in first] == [replay_key(p) for p in second]
    assert len({replay_key(p) for p in first}) == len(first)  # one key per incident
    assert replay_key(first[0], "ai1-prompt-v1") != replay_key(first[0])


@pytest.mark.parametrize(("dataset", "path"), [("fixture", FIXTURE), ("unsw-nb15", UNSW_SAMPLE)])
def test_recorded_answers_pass_the_normal_checks_in_another_upload(dataset, path):
    recording = record(dataset=dataset, path=path)
    assert all(e.valid for e in recording.entries)
    assert all(INCIDENT_PLACEHOLDER in e.raw_output for e in recording.entries)
    assert all("inc-" not in e.raw_output for e in recording.entries)
    generator = ReplayGenerator([recording])
    assert generator.accepts_messages is False  # the analysis job gives it one try
    for package in platform_packages(dataset, path, NOW, scope="upl-after-reset"):
        attempt = analyze_package(package, generator, clock=lambda: NOW, max_tries=1)
        assert attempt.valid, attempt.result.problems()
        report = attempt.result.report
        assert report.model_id == MODEL_PREFIX + "fake-27b"
        assert report.generated_by == "hpc" and report.incident_id == package.incident_id


def test_a_failed_answer_is_recorded_and_fails_again_on_replay():
    recording = record(Babbling())
    assert not any(e.valid for e in recording.entries)
    assert all(e.failure.startswith("P1") and e.raw_output for e in recording.entries)
    generator = ReplayGenerator([recording])
    package = platform_packages("fixture", FIXTURE, NOW, scope="upl-x")[0]
    attempt = analyze_package(package, generator, clock=lambda: NOW, max_tries=1)
    assert not attempt.valid and attempt.result.problems()[0].check == "P1"


def test_no_answer_and_no_recording_are_backend_errors_never_the_stub():
    silent = ReplayGenerator([record(Silent())])
    package = platform_packages("fixture", FIXTURE, NOW, scope="upl-x")[0]
    with pytest.raises(BackendError, match="gave no answer"):
        silent.generate([], package)
    partial = record()
    one = ReplayGenerator([partial.model_copy(update={"entries": partial.entries[:1]})])
    other = platform_packages("fixture", FIXTURE, NOW, scope="upl-x")[1]
    attempt = analyze_package(other, one, clock=lambda: NOW, max_tries=1)
    assert not attempt.valid and attempt.result.report is None


def test_recording_refuses_the_stub_and_a_replay():
    with pytest.raises(ValueError, match="not the stub"):
        record(StubGenerator())
    with pytest.raises(ValueError, match="from a replay"):
        record(ReplayGenerator([record()]))


def test_bad_recordings_are_refused():
    recording = record()
    with pytest.raises(ValueError, match="more than one model"):
        ReplayGenerator([recording, recording.model_copy(update={"model_id": "other"})])
    with pytest.raises(ValueError, match="prompt"):
        ReplayGenerator([recording.model_copy(update={"prompt_version": "ai1-prompt-v1"})])
    clash = recording.entries[0].model_copy(update={"raw_output": "{}"})
    with pytest.raises(ValueError, match="two different answers"):
        ReplayGenerator([recording.model_copy(update={"entries": [*recording.entries, clash]})])
    with pytest.raises(ValueError, match="at least one recording"):
        ReplayGenerator([])


def test_backend_is_chosen_from_the_environment(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_text(record().model_dump_json(), encoding="utf-8")
    generator = generator_from_env(
        {"ICD_ANALYSIS_BACKEND": "replay", "ICD_REPLAY_FILES": str(path)}
    )
    assert isinstance(generator, ReplayGenerator) and len(generator.answers) == 13


def test_record_command_refuses_the_stub(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ICD_ANALYSIS_BACKEND", "stub")
    assert main(["record", "fixture", str(FIXTURE), "--out", str(tmp_path / "r.json")]) == 1
    assert "not the stub" in capsys.readouterr().err


def test_committed_recordings_load_and_use_one_model():
    """Every file in app/analysis/replay_data/ must load as one set, as the worker loads it."""
    files = default_files()
    if not files:
        pytest.skip("no recordings committed yet")
    generator = ReplayGenerator(load_recordings(files))
    assert generator.answers and not generator.model_id.startswith(MODEL_PREFIX * 2)
