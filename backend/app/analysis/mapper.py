"""Map a checked LLM output v0 onto the AnalysisReport 1.0 contract (C3) without changing it.

What the contract has no place for (citations on the summary, weaknesses, impact, risk
justification and recommendations; the entity lists; the structured uncertainties) stays in the
raw LLM output, which the caller stores next to the report.
"""

from datetime import datetime
from typing import Literal

from app.analysis.output import LlmOutput, Recommendation
from app.contracts import AnalysisReport, EvidencePackage, Finding, SequenceStep


def _recommendation_text(rec: Recommendation) -> str:
    text = f"{rec.action} Why: {rec.rationale}"
    if rec.reversible_alternative:
        text += f" Less disruptive option: {rec.reversible_alternative}"
    return text


def _uncertainty_text(output: LlmOutput) -> str:
    parts = [
        f"{u.statement} (would be settled by: {u.missing_evidence})" for u in output.uncertainties
    ]
    parts.append("Limitations: " + " ".join(output.limitations))
    return " ".join(parts)


def to_report(
    output: LlmOutput,
    evidence: EvidencePackage,
    *,
    report_id: str,
    generated_at: datetime,
    generated_by: Literal["mock", "hpc", "local"],
    model_id: str | None,
    prompt_version: str | None,
    confidence: float,
) -> AnalysisReport:
    """Build the contract report. The backend fills the metadata and the computed confidence."""
    return AnalysisReport(
        report_id=report_id,
        incident_id=evidence.incident_id,
        evidence_package_id=evidence.package_id,
        generated_at=generated_at,
        generated_by=generated_by,
        model_id=model_id,
        prompt_version=prompt_version,
        summary=output.summary.text,
        attack_type=output.attack_type.category if output.attack_type else None,
        sequence=[
            SequenceStep(order=i, description=step.text, cited_event_ids=step.cited_event_ids)
            for i, step in enumerate(output.sequence, start=1)
        ]
        if output.sequence
        else None,
        findings=[
            Finding(statement=c.text, category=c.category, cited_event_ids=c.cited_event_ids)
            for c in output.findings
        ],
        weaknesses=[c.text for c in output.weaknesses] if output.weaknesses else None,
        impact=output.impact.text if output.impact else None,
        recommendations=[_recommendation_text(r) for r in output.recommendations],
        risk_justification=output.risk_justification.text if output.risk_justification else None,
        uncertainty=_uncertainty_text(output),
        confidence=confidence,
        model_self_rating=output.self_rating,
    )
