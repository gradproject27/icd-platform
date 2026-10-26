"""From raw model text to a valid AnalysisReport, or to a failed analysis (OD-09, FR-42).

A valid analysis is one where all of these hold:
  P1  the text holds one JSON object
  P2  the object matches LLM output v0 (types, required sections, citation rules)
  G*  the grounding check finds no hard problem (see grounding.py)
  M1  the mapped report passes the AnalysisReport 1.0 contract
Anything else is a failed analysis: no report, no confidence, no freeze.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import ValidationError

from app.analysis.confidence import compute_confidence
from app.analysis.grounding import GroundingResult, Problem, check_output, find_canaries
from app.analysis.mapper import to_report
from app.analysis.output import LlmOutput
from app.analysis.prompt import PROMPT_VERSION
from app.contracts import AnalysisReport, EvidencePackage
from app.llm.adapter import uncited_event_ids

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass(frozen=True)
class ReportMeta:
    """Values the backend fills, never the model."""

    report_id: str
    generated_at: datetime
    generated_by: Literal["mock", "hpc", "local"]
    model_id: str | None
    prompt_version: str | None = PROMPT_VERSION


@dataclass(frozen=True)
class AnalysisResult:
    output: LlmOutput | None
    grounding: GroundingResult | None
    report: AnalysisReport | None
    errors: tuple[Problem, ...] = field(default_factory=tuple)

    @property
    def valid(self) -> bool:
        return self.report is not None

    def problems(self) -> tuple[Problem, ...]:
        """Every hard problem, parse and mapping errors included."""
        return self.errors + (self.grounding.problems if self.grounding else ())


def parse_output(text: str) -> LlmOutput:
    """Parse the model text. Tolerates a code fence and a leading <think> block (Qwen3)."""
    text = THINK_BLOCK.sub("", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in the model output")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"model output is not valid JSON: {exc.msg}") from exc
    return LlmOutput.model_validate(data)


def run_analysis(text: str, evidence: EvidencePackage, meta: ReportMeta) -> AnalysisResult:
    """Parse, check, score and map one model answer."""
    try:
        output = parse_output(text)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()
        )
        return AnalysisResult(None, None, None, (Problem("P2", "output", details),))
    except ValueError as exc:
        return AnalysisResult(None, None, None, (Problem("P1", "output", str(exc)),))

    grounding = check_output(output, evidence, find_canaries(evidence))
    confidence = compute_confidence(output, grounding, evidence)
    if confidence is None:
        return AnalysisResult(output, grounding, None)

    try:
        report = to_report(
            output,
            evidence,
            report_id=meta.report_id,
            generated_at=meta.generated_at,
            generated_by=meta.generated_by,
            model_id=meta.model_id,
            prompt_version=meta.prompt_version,
            confidence=confidence,
        )
    except ValidationError as exc:
        return AnalysisResult(output, grounding, None, (Problem("M1", "report", str(exc)),))
    if uncited_event_ids(report, evidence):
        return AnalysisResult(output, grounding, None, (Problem("M1", "report", "uncited IDs"),))
    return AnalysisResult(output, grounding, report)
