"""AI1 analysis layer: LLM output v0, grounding checks, confidence and mapping to AnalysisReport.

Pure functions only: no network, no clock, no model. The LLM backends (C1's adapter) send the
prompt from `prompt.py` and pass the raw model text to `run_analysis`.
"""

from app.analysis.confidence import compute_confidence, evidence_completeness
from app.analysis.grounding import GroundingResult, Problem, check_output, find_canaries
from app.analysis.mapper import to_report
from app.analysis.output import (
    OUTPUT_VERSION,
    AnalysisOutcome,
    AttackType,
    Claim,
    Entities,
    LlmOutput,
    Recommendation,
    Uncertainty,
)
from app.analysis.pipeline import AnalysisResult, ReportMeta, parse_output, run_analysis
from app.analysis.prompt import PROMPT_VERSION, build_messages

__all__ = [
    "OUTPUT_VERSION",
    "PROMPT_VERSION",
    "AnalysisOutcome",
    "AnalysisResult",
    "AttackType",
    "Claim",
    "Entities",
    "GroundingResult",
    "LlmOutput",
    "Problem",
    "Recommendation",
    "ReportMeta",
    "Uncertainty",
    "build_messages",
    "check_output",
    "compute_confidence",
    "evidence_completeness",
    "find_canaries",
    "parse_output",
    "run_analysis",
    "to_report",
]
