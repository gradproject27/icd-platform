"""Worker side of the confidence HPC batch job (risk-v1 step 6b, user decision of 26 Nov 2026).

The same Slurm handoff as the AI report (app/hpc/batch.py, decision F4): scp the input file,
sbatch tools/confidence/icd_confidence.sbatch, poll squeue, scp the output back. Turned on by

    ICD_CONFIDENCE_BACKEND          off (default) | hpc_batch
    ICD_CONFIDENCE_SBATCH_SCRIPT    path of icd_confidence.sbatch on the cluster
    ICD_HPC_SSH_TARGET, ICD_HPC_SSH_KEY, ICD_HPC_REMOTE_DIR, ICD_HPC_POLL_SECONDS,
    ICD_HPC_TIMEOUT_SECONDS         shared with the AI report handoff

With the backend off, nothing changes: incidents keep the risk-v0 score and no confidence job
is queued.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError

from app.analysis.backends import BackendError
from app.api.schemas import JobStage
from app.confidence.handoff import ConfidenceOutput
from app.hpc.batch import HpcBatchConfig, HpcBatchGenerator, _fail


def enabled(env: Mapping[str, str]) -> bool:
    backend = (env.get("ICD_CONFIDENCE_BACKEND") or "off").strip()
    if backend not in ("off", "hpc_batch"):
        raise ValueError(f"unknown ICD_CONFIDENCE_BACKEND {backend!r}; use off or hpc_batch")
    return backend == "hpc_batch"


def config_from_env(env: Mapping[str, str]) -> HpcBatchConfig:
    script = env.get("ICD_CONFIDENCE_SBATCH_SCRIPT")
    if not script:
        raise ValueError("hpc_batch confidence needs ICD_CONFIDENCE_SBATCH_SCRIPT")
    base = {**env, "ICD_HPC_SBATCH_SCRIPT": script,
            "ICD_HPC_MODEL": env.get("ICD_HPC_MODEL") or "confidence"}  # fmt: skip
    return replace(HpcBatchConfig.from_env(base), sbatch_script=script)


@dataclass
class ConfidenceBatch(HpcBatchGenerator):
    """Submits one confidence input file and returns the cluster's output."""

    def submit(self, data: dict[str, Any]) -> ConfidenceOutput:
        name = data["request_id"]
        remote_in = f"{self.config.remote_dir}/{name}.confidence-in.json"
        remote_out = f"{self.config.remote_dir}/{name}.confidence-out.json"
        self.staging.mkdir(parents=True, exist_ok=True)
        local_in = self.staging / f"{name}.confidence-in.json"
        local_out = self.staging / f"{name}.confidence-out.json"
        local_in.write_text(json.dumps(data), encoding="utf-8")
        local_out.unlink(missing_ok=True)
        target = self.config.ssh_target

        made = self._ssh(["mkdir", "-p", self.config.remote_dir])
        if made.returncode != 0:
            raise _fail("hpc_unreachable", f"ssh {target} failed: {made.stderr.strip()[:300]}")
        self._ssh(["rm", "-f", remote_out])
        sent = self._scp(str(local_in), f"{target}:{remote_in}")
        if sent.returncode != 0:
            raise _fail("hpc_unreachable", f"copy failed: {sent.stderr.strip()[:300]}")
        submitted = self._ssh(
            [
                "sbatch", "--parsable", f"--job-name=icd-conf-{name[:36]}",
                f"--export=ALL,ICD_CONFIDENCE_INPUT={remote_in},ICD_CONFIDENCE_OUTPUT={remote_out}",
                self.config.sbatch_script,
            ]
        )  # fmt: skip
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
            output = ConfidenceOutput.model_validate_json(local_out.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise _fail("hpc_job_failed", f"unreadable output file: {exc}") from None
        if output.request_id != name:
            raise _fail("hpc_job_failed", f"output answers {output.request_id}, not {name}")
        return output


__all__ = ["BackendError", "ConfidenceBatch", "config_from_env", "enabled"]
