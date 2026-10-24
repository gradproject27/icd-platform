"""LLM adapter interface.

Callers depend on LLMAnalyzer, never on a concrete backend, so the rest of ICD runs
with the mock when no LLM or HPC is available.
"""

import os
from typing import Protocol, runtime_checkable

from app.contracts import AnalysisReport, EvidencePackage
from app.llm.mock import MockAnalyzer


@runtime_checkable
class LLMAnalyzer(Protocol):
    def analyze(self, evidence: EvidencePackage) -> AnalysisReport: ...


def uncited_event_ids(report: AnalysisReport, evidence: EvidencePackage) -> list[str]:
    """Return the event IDs the report cites that are not in the evidence, sorted.

    Checks the citations of every finding and every sequence step.
    """
    cited = {event_id for finding in report.findings for event_id in finding.cited_event_ids}
    cited |= {event_id for step in report.sequence or [] for event_id in step.cited_event_ids}
    return sorted(cited - evidence.citable_event_ids())


def get_analyzer() -> LLMAnalyzer:
    """Pick the backend from LLM_BACKEND. Only "mock" exists for now."""
    backend = os.environ.get("LLM_BACKEND") or "mock"
    if backend == "mock":
        return MockAnalyzer()
    raise ValueError(f"Unsupported LLM_BACKEND {backend!r}; only 'mock' is available")
