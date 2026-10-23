"""Provisional LLM contracts.

TODO(C3, AI1): this whole module is replaced by C3's frozen contracts in contracts/
(M1 gate). It exists only so the adapter and the mock can be built and tested now.
No other module may define these models; import them from here until then.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceEvent(_Strict):
    event_id: str
    timestamp: datetime
    source: str
    summary: str


class EvidencePackage(_Strict):
    incident_id: str
    events: list[EvidenceEvent]


class Finding(_Strict):
    statement: str
    cited_event_ids: list[str] = Field(min_length=1)


class AnalysisReport(_Strict):
    incident_id: str
    findings: list[Finding]
    uncertainty: str
    recommendations: list[str]
    confidence: float = Field(ge=0, le=1)
    generated_by: Literal["mock", "hpc", "local"]
