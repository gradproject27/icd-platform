"""Analysis confidence (OD-16), computed by the analysis component, never by the model.

confidence = grounding_rate * (GROUNDING_FLOOR + (1 - GROUNDING_FLOOR) * completeness)

- grounding_rate: share of factual claims whose cited events carry every entity they name.
- completeness: share of the key fields (host, src_ip, user) present on the flagged events.

With every claim grounded, full key fields give 1.0 and no key fields give 0.6, so thin evidence
alone never reaches the 0.75 freeze gate. An insufficient_evidence output gets 0.0. The value is a
score from 0 to 1, not a calibrated probability. GROUNDING_FLOOR is a proposal (AI1, Week 1).
"""

from app.analysis.grounding import GroundingResult
from app.analysis.output import AnalysisOutcome, LlmOutput
from app.contracts import EventRole, EvidencePackage

GROUNDING_FLOOR = 0.6
KEY_FIELDS = ("host", "src_ip", "user")


def evidence_completeness(evidence: EvidencePackage) -> float:
    """Share of key fields present on the flagged events (all events if none is flagged)."""
    events = [e for e in evidence.events if e.role == EventRole.FLAGGED] or list(evidence.events)
    if not events:
        return 0.0
    present = sum(getattr(event, name) is not None for event in events for name in KEY_FIELDS)
    return present / (len(events) * len(KEY_FIELDS))


def compute_confidence(
    output: LlmOutput, grounding: GroundingResult, evidence: EvidencePackage
) -> float | None:
    """Confidence for a valid analysis; None when the analysis is not valid (FR-42)."""
    if not grounding.valid:
        return None
    if output.analysis_status == AnalysisOutcome.INSUFFICIENT_EVIDENCE:
        return 0.0
    completeness = evidence_completeness(evidence)
    value = grounding.grounding_rate * (GROUNDING_FLOOR + (1 - GROUNDING_FLOOR) * completeness)
    return round(value, 4)
