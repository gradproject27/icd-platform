"""Deterministic mock analyzer.

Same input, same output: no clock, no randomness, no network. It restates each
evidence event as an evidence-supported finding that cites only that event, so it
never cites an ID that is not in the input. All text is marked [MOCK]. It cannot read
a clock, so generated_at is copied from the evidence package's created_at.
"""

from app.contracts import AnalysisReport, EvidencePackage, Finding, FindingCategory


class MockAnalyzer:
    def analyze(self, evidence: EvidencePackage) -> AnalysisReport:
        findings = [
            Finding(
                statement=f"[MOCK] {event.source} reported: {event.summary}",
                category=FindingCategory.EVIDENCE_SUPPORTED,
                cited_event_ids=[event.event_id],
            )
            for event in evidence.events
        ]
        if findings:
            summary = (
                f"[MOCK] Incident {evidence.incident_id}: {len(findings)} evidence events "
                "restated without interpretation."
            )
            uncertainty = (
                "[MOCK] Produced by the deterministic mock, not an LLM. It restates the "
                "evidence and draws no conclusions."
            )
            recommendations = [
                f"[MOCK] [SIMULATED] Analyst reviews the cited events for incident "
                f"{evidence.incident_id}. No action is executed."
            ]
        else:
            summary = f"[MOCK] Incident {evidence.incident_id}: no evidence events were provided."
            uncertainty = "[MOCK] No evidence events were provided, so there are no findings."
            recommendations = []
        return AnalysisReport(
            report_id=f"mock-{evidence.package_id}"[:128],
            incident_id=evidence.incident_id,
            evidence_package_id=evidence.package_id,
            generated_at=evidence.created_at,
            generated_by="mock",
            summary=summary,
            findings=findings,
            recommendations=recommendations,
            uncertainty=uncertainty,
            confidence=0.0,
        )
