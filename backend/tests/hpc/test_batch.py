"""C1 HPC batch handoff against a fake Slurm cluster (decision F4). No real HPC is used: the
team has no access, so these tests are the only runs of this code so far."""

import json
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.analysis.backends import BackendError, generator_from_env
from app.analysis.service import analyze_package
from app.analysis.stub import stub_output
from app.api.schemas import JobStage
from app.contracts import EvidencePackage
from app.hpc.batch import HpcBatchConfig, HpcBatchGenerator

PACKAGES = Path(__file__).resolve().parents[3] / "fixtures" / "ai1" / "packages"
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def package() -> EvidencePackage:
    first = sorted(PACKAGES.glob("*.json"))[0]
    return EvidencePackage.model_validate_json(first.read_text(encoding="utf-8"))


class FakeCluster:
    """Answers ssh and scp like a login node with Slurm; files live under `root`."""

    def __init__(self, root: Path, *, mode: str = "ok", polls_running: int = 1) -> None:
        self.root, self.mode, self.polls_running = root, mode, polls_running
        self.calls: list[list[str]] = []
        self.cancelled: list[str] = []

    def path(self, remote: str) -> Path:
        return self.root / remote.lstrip("/")

    def __call__(self, args: list[str], timeout: float) -> subprocess.CompletedProcess:
        self.calls.append(args)
        if self.mode == "unreachable":
            return subprocess.CompletedProcess(args, 255, "", "ssh: connect: Connection refused")
        if args[0] == "scp":
            source, target = args[-2], args[-1]
            if ":" in source:
                src = self.path(source.split(":", 1)[1])
                if not src.exists():
                    return subprocess.CompletedProcess(args, 1, "", "No such file")
                Path(target).write_bytes(src.read_bytes())
            else:
                dst = self.path(target.split(":", 1)[1])
                dst.write_bytes(Path(source).read_bytes())
            return subprocess.CompletedProcess(args, 0, "", "")
        command = shlex.split(args[-1])
        return getattr(self, command[0])(args, command[1:])

    def mkdir(self, args, rest):
        self.path(rest[-1]).mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(args, 0, "", "")

    def rm(self, args, rest):
        self.path(rest[-1]).unlink(missing_ok=True)
        return subprocess.CompletedProcess(args, 0, "", "")

    def sbatch(self, args, rest):
        export = next(r for r in rest if r.startswith("--export="))
        values = dict(item.split("=", 1) for item in export.split(",")[1:])
        evidence = EvidencePackage.model_validate_json(
            self.path(values["ICD_EVIDENCE"]).read_text()
        )
        if self.mode != "no_output":
            body = {
                "format": "icd-hpc-output-v1",
                "package_id": evidence.package_id,
                "incident_id": evidence.incident_id,
                "generated_by": "hpc",
                "model_id": "Qwen/Qwen3-8B@abc123",
                "prompt_version": "v2",
                "started_at": "2026-11-24T12:00:00Z",
                "finished_at": "2026-11-24T12:01:00Z",
            }
            if self.mode == "model_error":
                body["error"] = "CUDA out of memory"
            else:
                body["raw_output"] = json.dumps(stub_output(evidence))
            self.path(values["ICD_OUTPUT"]).write_text(json.dumps(body))
        return subprocess.CompletedProcess(args, 0, "4242\n", "")

    def squeue(self, args, rest):
        if self.mode == "stuck" or self.polls_running > 0:
            self.polls_running -= 1
            return subprocess.CompletedProcess(args, 0, "RUNNING\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    def scancel(self, args, rest):
        self.cancelled.append(rest[0])
        return subprocess.CompletedProcess(args, 0, "", "")


CONFIG = HpcBatchConfig(
    ssh_target="icd@login.hpc.example",
    remote_dir="/scratch/icd/jobs",
    sbatch_script="/scratch/icd/icd_analyze.sbatch",
    model_id="Qwen/Qwen3-8B@abc123",
    poll_seconds=30,
    timeout_seconds=120,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def generator(cluster: FakeCluster, tmp_path: Path, stages: list | None = None):
    clock = Clock()
    return HpcBatchGenerator(
        CONFIG,
        run=cluster,
        sleep=clock.sleep,
        monotonic=lambda: clock.now,
        staging=tmp_path / "staging",
        on_stage=None if stages is None else stages.append,
    )


def test_a_package_goes_to_the_cluster_and_a_checked_report_comes_back(tmp_path):
    cluster = FakeCluster(tmp_path / "cluster")
    stages: list[JobStage] = []
    gen = generator(cluster, tmp_path, stages)

    attempt = analyze_package(package(), gen, clock=lambda: NOW, max_tries=1)

    assert attempt.valid, attempt.problems()
    assert attempt.result.report.generated_by == "hpc"
    assert attempt.result.report.model_id == CONFIG.model_id
    assert stages == [JobStage.WAITING_HPC, JobStage.COLLECTING]
    sbatch = next(c for c in cluster.calls if c[0] == "ssh" and "sbatch" in c[-1])
    assert "BatchMode=yes" in sbatch  # never waits for a password prompt
    assert "ICD_EVIDENCE=/scratch/icd/jobs/" in sbatch[-1]


def test_only_the_masked_package_leaves_the_app_host(tmp_path):
    cluster = FakeCluster(tmp_path / "cluster")
    evidence = package()
    generator(cluster, tmp_path).generate([], evidence)
    sent = json.loads((cluster.root / "scratch/icd/jobs" / f"{evidence.package_id}.evidence.json")
                      .read_text())  # fmt: skip
    assert sent["masked"] is True


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("unreachable", "hpc_unreachable"),
        ("no_output", "report_missing"),
        ("model_error", "hpc_job_failed"),
    ],
)
def test_each_failure_names_its_job_error_code(tmp_path, mode, code):
    with pytest.raises(BackendError, match=f"^{code}: "):
        generator(FakeCluster(tmp_path / "cluster", mode=mode), tmp_path).generate([], package())


def test_a_job_that_never_ends_is_cancelled_at_the_timeout(tmp_path):
    cluster = FakeCluster(tmp_path / "cluster", mode="stuck")
    with pytest.raises(BackendError, match="^hpc_timeout: "):
        generator(cluster, tmp_path).generate([], package())
    assert cluster.cancelled == ["4242"]
    polls = [c for c in cluster.calls if c[0] == "ssh" and c[-1].startswith("squeue")]
    assert len(polls) == 120 // 30 + 1  # every 30 s for 2 minutes, then cancel


def test_a_stale_answer_from_an_earlier_attempt_is_removed_first(tmp_path):
    cluster = FakeCluster(tmp_path / "cluster", mode="no_output")
    evidence = package()
    stale = cluster.root / "scratch/icd/jobs" / f"{evidence.package_id}.output.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    with pytest.raises(BackendError, match="^report_missing: "):
        generator(cluster, tmp_path).generate([], evidence)


def test_the_environment_selects_hpc_batch_and_names_what_is_missing():
    env = {
        "ICD_ANALYSIS_BACKEND": "hpc_batch",
        "ICD_HPC_SSH_TARGET": "icd@login",
        "ICD_HPC_REMOTE_DIR": "/scratch/icd/",
        "ICD_HPC_SBATCH_SCRIPT": "/scratch/icd/icd_analyze.sbatch",
        "ICD_HPC_MODEL": "Qwen/Qwen3-8B@abc",
    }
    gen = generator_from_env(env)
    assert isinstance(gen, HpcBatchGenerator)
    assert gen.config.remote_dir == "/scratch/icd" and gen.config.poll_seconds == 30
    assert gen.accepts_messages is False
    with pytest.raises(ValueError, match="ICD_HPC_MODEL"):
        generator_from_env({k: v for k, v in env.items() if k != "ICD_HPC_MODEL"})
