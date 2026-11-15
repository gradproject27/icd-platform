"""HPC handoff files (AI1 to C1): the evidence file in, the output file `icd-hpc-output-v1` out.

Evidence file: one EvidencePackage 1.0 as JSON, masked (C2's builder; masked=false is refused).
Output file: `HpcOutput` below, written by `tools/ai1/icd_analyze.py` on the cluster (the command
C1's sbatch script runs) and read back on the app host, where `analyze_hpc_output` turns it into
an AnalysisReport or a failed analysis. The model's text is checked only on the app host.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analysis.grounding import Problem
from app.analysis.pipeline import AnalysisResult, ReportMeta, run_analysis
from app.contracts import EvidencePackage
from app.contracts.common import Id, JsonScalar, NonEmptyStr, UtcDatetime

HPC_OUTPUT_FORMAT = "icd-hpc-output-v1"


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int | None = Field(default=None, ge=0, description="Prompt tokens, if known.")
    completion_tokens: int | None = Field(
        default=None, ge=0, description="Generated tokens, if known."
    )


class HpcOutput(BaseModel):
    """One model run for one evidence package, as the cluster writes it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["icd-hpc-output-v1"] = Field(description="File format and version.")
    package_id: Id = Field(description="The evidence package this run answers.")
    incident_id: Id = Field(description="Copied from the package.")
    generated_by: Literal["hpc", "local"] = Field(description="Where the model ran.")
    model_id: NonEmptyStr = Field(description="Pinned model, <repo>@<commit> or the served name.")
    prompt_version: NonEmptyStr = Field(description="Prompt version the runner sent.")
    raw_output: str | None = Field(
        default=None, description="The model's answer exactly as returned; null when error is set."
    )
    error: NonEmptyStr | None = Field(
        default=None, description="Why the run failed (for example out of GPU memory)."
    )
    started_at: UtcDatetime = Field(description="Start of inference, UTC.")
    finished_at: UtcDatetime = Field(description="End of inference, UTC.")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token counts, if known.")
    settings: dict[str, JsonScalar] = Field(
        default_factory=dict,
        description="Generation settings used, for example temperature and max_new_tokens.",
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.raw_output is None) == (self.error is None):
            raise ValueError("exactly one of raw_output and error must be set")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not be before started_at")
        return self


def analyze_hpc_output(
    output: HpcOutput, evidence: EvidencePackage, report_id: str
) -> AnalysisResult:
    """Check one output file against the package it answers. A run error is a failed analysis."""
    if output.package_id != evidence.package_id or output.incident_id != evidence.incident_id:
        detail = f"answers {output.package_id}, not {evidence.package_id}"
        return AnalysisResult(None, None, None, (Problem("H1", "output file", detail),))
    if output.raw_output is None:
        return AnalysisResult(None, None, None, (Problem("H2", "output file", str(output.error)),))
    meta = ReportMeta(
        report_id=report_id,
        generated_at=output.finished_at,
        generated_by=output.generated_by,
        model_id=output.model_id,
        prompt_version=output.prompt_version,
    )
    return run_analysis(output.raw_output, evidence, meta)
