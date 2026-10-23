"""Deterministic mock analyzer.

Same input, same output: no clock, no randomness, no network. It restates each
evidence event as a finding that cites only that event, so it never cites an ID
that is not in the input. All text is marked [MOCK].
"""

from app.llm.contracts import AnalysisReport, EvidencePackage, Finding


class MockAnalyzer:
    def analyze(self, evidence: EvidencePackage) -> AnalysisReport:
        findings = [
            Finding(
                statement=f"[MOCK] {event.source} reported: {event.summary}",
                cited_event_ids=[event.event_id],
            )
            for event in evidence.events
        ]
        if findings:
            uncertainty = (
                "[MOCK] Produced by the deterministic mock, not an LLM. It restates the "
                "evidence and draws no conclusions."
            )
            recommendations = [
                f"[MOCK] [SIMULATED] Analyst reviews the cited events for incident "
                f"{evidence.incident_id}. No action is executed."
            ]
        else:
            uncertainty = "[MOCK] No evidence events were provided, so there are no findings."
            recommendations = []
        return AnalysisReport(
            incident_id=evidence.incident_id,
            findings=findings,
            uncertainty=uncertainty,
            recommendations=recommendations,
            confidence=0.0,
            generated_by="mock",
        )
