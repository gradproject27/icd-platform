"""C1 HPC batch handoff (decision F4): one masked evidence file to a Slurm cluster, one
`icd-hpc-output-v1` file back. Built for the national HPC once access exists; until then it is
tested only against a fake cluster (tests/hpc/test_batch.py) and has NOT been run on a real one.

    1. write   <staging>/<package_id>.evidence.json     (masked package; masked=false refused
                                                          earlier by the analysis service, S1)
    2. scp     -> <remote_dir>/<package_id>.evidence.json
    3. ssh     sbatch --parsable --export=ALL,ICD_EVIDENCE=..,ICD_OUTPUT=.. <sbatch script>
               (tools/c1/icd_analyze.sbatch runs AI1's tools/ai1/icd_analyze.py)
    4. ssh     squeue -h -j <id> -o %T, every poll interval, until the job leaves the queue;
               after the timeout: scancel and fail with hpc_timeout
    5. scp     <- <remote_dir>/<package_id>.output.json; missing -> report_missing
    6. read    HpcOutput; its error set or another package's answer -> hpc_job_failed

The model's text is returned as a Generation and checked on the app host like any other
backend's answer (app.analysis.service). A failure is a BackendError whose message starts
with the job error code (hpc_unreachable, hpc_timeout, hpc_job_failed, report_missing), which
the analysis job turns into its failure code after the retries (app/jobs/analysis.py).

Environment (ICD_ANALYSIS_BACKEND=hpc_batch):

    ICD_HPC_SSH_TARGET      user@login-node (key-based login; no password prompt)
    ICD_HPC_SSH_KEY         optional private key path inside the worker container
    ICD_HPC_REMOTE_DIR      working directory on the cluster, for example /scratch/<user>/icd
    ICD_HPC_SBATCH_SCRIPT   path of the sbatch script on the cluster
    ICD_HPC_MODEL           the model pin the script runs, <repo>@<commit>
    ICD_HPC_POLL_SECONDS    default 30 (decision D17 of Week 2)
    ICD_HPC_TIMEOUT_SECONDS default 7200 (120 minutes, D17)
"""

import shlex
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.analysis.backends import BackendError, Generation
from app.analysis.handoff import HpcOutput
from app.api.schemas import JobStage
from app.contracts import EvidencePackage

Run = Callable[[list[str], float], subprocess.CompletedProcess]


def run_command(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    """Run ssh or scp without a shell; output captured as text."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


@dataclass(frozen=True)
class HpcBatchConfig:
    ssh_target: str
    remote_dir: str
    sbatch_script: str
    model_id: str
    ssh_key: str | None = None
    poll_seconds: float = 30
    timeout_seconds: float = 7200
    command_timeout_seconds: float = 120

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "HpcBatchConfig":
        missing = [
            name
            for name in (
                "ICD_HPC_SSH_TARGET",
                "ICD_HPC_REMOTE_DIR",
                "ICD_HPC_SBATCH_SCRIPT",
                "ICD_HPC_MODEL",
            )
            if not env.get(name)
        ]
        if missing:
            raise ValueError(f"hpc_batch needs {', '.join(missing)}")
        return cls(
            ssh_target=env["ICD_HPC_SSH_TARGET"],
            remote_dir=env["ICD_HPC_REMOTE_DIR"].rstrip("/"),
            sbatch_script=env["ICD_HPC_SBATCH_SCRIPT"],
            model_id=env["ICD_HPC_MODEL"],
            ssh_key=env.get("ICD_HPC_SSH_KEY") or None,
            poll_seconds=float(env.get("ICD_HPC_POLL_SECONDS", "30")),
            timeout_seconds=float(env.get("ICD_HPC_TIMEOUT_SECONDS", "7200")),
        )


def _fail(code: str, detail: str) -> BackendError:
    return BackendError(f"{code}: {detail}")


@dataclass
class HpcBatchGenerator:
    """The `hpc_batch` backend (module docstring)."""

    config: HpcBatchConfig
    run: Run = run_command
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    staging: Path = field(default_factory=lambda: Path(tempfile.gettempdir()) / "icd-hpc")
    # Set by the analysis job to show waiting_hpc / collecting on GET /jobs/{id}.
    on_stage: Callable[[JobStage], object] | None = None

    generated_by = "hpc"
    # The cluster builds the prompt itself from the evidence file, so the schema-retry turn
    # (repair messages) cannot be sent; the analysis job then allows one try.
    accepts_messages = False

    @property
    def model_id(self) -> str:
        return self.config.model_id

    # ---- commands ------------------------------------------------------------------------

    def _ssh_options(self) -> list[str]:
        options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
        if self.config.ssh_key:
            options += ["-i", self.config.ssh_key]
        return options

    def _ssh(self, remote_command: list[str]) -> subprocess.CompletedProcess:
        command = " ".join(shlex.quote(part) for part in remote_command)
        args = ["ssh", *self._ssh_options(), self.config.ssh_target, command]
        return self._call(args)

    def _scp(self, source: str, target: str) -> subprocess.CompletedProcess:
        return self._call(["scp", "-q", *self._ssh_options(), source, target])

    def _call(self, args: list[str]) -> subprocess.CompletedProcess:
        try:
            return self.run(args, self.config.command_timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise _fail("hpc_unreachable", f"{args[0]} did not complete: {exc}") from None

    def _stage(self, stage: JobStage) -> None:
        if self.on_stage is not None:
            self.on_stage(stage)

    # ---- the handoff ---------------------------------------------------------------------

    def generate(self, messages: list[dict[str, str]], evidence: EvidencePackage) -> Generation:
        name = evidence.package_id
        remote_in = f"{self.config.remote_dir}/{name}.evidence.json"
        remote_out = f"{self.config.remote_dir}/{name}.output.json"
        self.staging.mkdir(parents=True, exist_ok=True)
        local_in = self.staging / f"{name}.evidence.json"
        local_out = self.staging / f"{name}.output.json"
        local_in.write_text(evidence.model_dump_json(), encoding="utf-8")
        local_out.unlink(missing_ok=True)

        target = self.config.ssh_target
        made = self._ssh(["mkdir", "-p", self.config.remote_dir])
        if made.returncode != 0:
            raise _fail("hpc_unreachable", f"ssh {target} failed: {made.stderr.strip()[:300]}")
        # A stale answer from an earlier attempt must not be read as this one's.
        self._ssh(["rm", "-f", remote_out])
        sent = self._scp(str(local_in), f"{target}:{remote_in}")
        if sent.returncode != 0:
            raise _fail(
                "hpc_unreachable", f"copy to the cluster failed: {sent.stderr.strip()[:300]}"
            )

        submitted = self._ssh(
            [
                "sbatch",
                "--parsable",
                f"--job-name=icd-{name[:40]}",
                f"--export=ALL,ICD_EVIDENCE={remote_in},ICD_OUTPUT={remote_out}",
                self.config.sbatch_script,
            ]
        )
        slurm_id = submitted.stdout.strip().split(";", 1)[0]
        if submitted.returncode != 0 or not slurm_id.isdigit():
            detail = (submitted.stderr or submitted.stdout).strip()[:300]
            raise _fail("hpc_job_failed", f"sbatch refused the job: {detail}")

        self._stage(JobStage.WAITING_HPC)
        self._wait(slurm_id)

        self._stage(JobStage.COLLECTING)
        fetched = self._scp(f"{target}:{remote_out}", str(local_out))
        if fetched.returncode != 0 or not local_out.exists():
            raise _fail("report_missing", f"Slurm job {slurm_id} ended without {remote_out}")
        try:
            output = HpcOutput.model_validate_json(local_out.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise _fail("hpc_job_failed", f"unreadable output file: {exc}") from None
        if output.package_id != evidence.package_id:
            raise _fail("hpc_job_failed", f"output answers {output.package_id}, not {name}")
        if output.raw_output is None:
            raise _fail("hpc_job_failed", f"the model run failed: {output.error}")
        return Generation(
            output.raw_output, output.usage.prompt_tokens, output.usage.completion_tokens
        )

    def _wait(self, slurm_id: str) -> None:
        deadline = self.monotonic() + self.config.timeout_seconds
        while True:
            queued = self._ssh(["squeue", "-h", "-j", slurm_id, "-o", "%T"])
            # squeue answers nothing (or an "Invalid job id" error) once the job has left the
            # queue; any other ssh failure is retried at the next poll until the deadline.
            if queued.returncode == 0 and not queued.stdout.strip():
                return
            if queued.returncode != 0 and "invalid job id" in queued.stderr.lower():
                return
            if self.monotonic() >= deadline:
                self._ssh(["scancel", slurm_id])
                minutes = self.config.timeout_seconds / 60
                raise _fail(
                    "hpc_timeout", f"Slurm job {slurm_id} still queued after {minutes:g} min"
                )
            self.sleep(self.config.poll_seconds)
