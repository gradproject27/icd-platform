"""AnalysisReport: the AI's structured result for one incident (FR-14, FR-15, FR-42, OD-16)."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.contracts.common import Id, NonEmptyStr, UtcDatetime, _Contract

Fraction = Annotated[float, Field(ge=0, le=1)]


class FindingCategory(StrEnum):
    """How strongly a finding is supported (FR-15)."""

    EVIDENCE_SUPPORTED = "evidence_supported"
    LIKELY_INTERPRETATION = "likely_interpretation"
    HYPOTHESIS = "hypothesis"


class SequenceStep(_Contract):
    """One step of the possible sequence of events."""

    order: int = Field(ge=1, description="Position in the sequence: 1, 2, 3, ... with no gaps.")
    description: NonEmptyStr = Field(description="What happened in this step.")
    cited_event_ids: list[Id] = Field(
        min_length=1, description="Evidence event IDs that support the step."
    )


class Finding(_Contract):
    """One suspicious behaviour with its evidence (FR-14, FR-15)."""

    statement: NonEmptyStr = Field(description="The finding.")
    category: FindingCategory = Field(description="Evidence-supported, likely or hypothesis.")
    cited_event_ids: list[Id] = Field(
        description="Evidence event IDs. At least one for evidence_supported (FR-15)."
    )

    @model_validator(mode="after")
    def _evidence_supported_cites(self) -> Self:
        if self.category == FindingCategory.EVIDENCE_SUPPORTED and not self.cited_event_ids:
            raise ValueError("an evidence_supported finding must cite at least one event")
        return self


class GroundingCounts(_Contract):
    """How many claims of the report the grounding check could tie to the evidence (R2, 1.3).

    A claim is one statement of the model's answer: the summary, the attack type, each sequence
    step, finding and weakness, the impact and the risk justification. Factual claims are the
    evidence_supported and likely_interpretation ones; a hypothesis is never counted as
    supported or unsupported. A factual claim is supported when every host, IP and user it
    names is in the events it cites, and unsupported otherwise (AI1 check U1).
    """

    claims: int = Field(ge=0, description="All claims, hypotheses included.")
    factual_claims: int = Field(ge=0, description="evidence_supported + likely_interpretation.")
    grounded_factual_claims: int = Field(
        ge=0, description="Factual claims whose cited events carry every entity they name."
    )
    unsupported: int = Field(
        ge=0, description="Factual claims that name an entity their cited events do not carry."
    )

    @model_validator(mode="after")
    def _counts_add_up(self) -> Self:
        if self.grounded_factual_claims + self.unsupported != self.factual_claims:
            raise ValueError("grounded_factual_claims + unsupported must equal factual_claims")
        if self.factual_claims > self.claims:
            raise ValueError("factual_claims must not exceed claims")
        return self


class AnalysisReport(_Contract):
    """The AI's structured result for one incident. null in a section means not determined."""

    schema_version: Literal["1.0"] = Field(default="1.0", description="Contract version.")
    report_id: Id = Field(description="Unique report ID.")
    incident_id: Id = Field(description="ID of the analysed incident.")
    evidence_package_id: Id = Field(description="The EvidencePackage the report came from.")
    generated_at: UtcDatetime = Field(description="When the report was produced, UTC.")
    generated_by: Literal["mock", "hpc", "local"] = Field(description="Analyzer backend.")
    model_id: NonEmptyStr | None = Field(
        default=None, description="Pinned model name; null for the mock."
    )
    prompt_version: NonEmptyStr | None = Field(
        default=None, description="Prompt version; null for the mock."
    )
    summary: NonEmptyStr = Field(description="Concise summary (FR-14).")
    attack_type: NonEmptyStr | None = Field(
        default=None, description="Suspected attack type or category; null = not determined."
    )
    sequence: Annotated[list[SequenceStep], Field(min_length=1)] | None = Field(
        default=None, description="Possible sequence of events; null = not determined."
    )
    findings: list[Finding] = Field(
        description="Suspicious behaviour with evidence; empty when there is no evidence."
    )
    weaknesses: Annotated[list[NonEmptyStr], Field(min_length=1)] | None = Field(
        default=None,
        description="Weaknesses, only when the evidence supports them; null = not determined.",
    )
    impact: NonEmptyStr | None = Field(
        default=None, description="Possible impact; null = not determined."
    )
    recommendations: list[NonEmptyStr] = Field(
        description="Free text for the analyst. Never drives an action (C-10)."
    )
    risk_justification: NonEmptyStr | None = Field(
        default=None,
        description="Explains the deterministic score; the report has no score (FR-19). "
        "null = not determined.",
    )
    uncertainty: NonEmptyStr = Field(description="Uncertainty and limitations (FR-15).")
    confidence: Fraction = Field(
        description="Computed by the analysis component from grounding and evidence "
        "completeness, not by the model (OD-16). The mock sets 0.0."
    )
    model_self_rating: Fraction | None = Field(
        default=None,
        description="The model's own rating. Stored, never used for the 0.75 gate (OD-16).",
    )
    grounding: GroundingCounts | None = Field(
        default=None,
        description="Supported and unsupported claim counts behind the confidence (R2, 1.3). "
        "null = not recorded (the mock, reports from before 1.3).",
    )

    @model_validator(mode="after")
    def _sequence_has_no_gaps(self) -> Self:
        if self.sequence is not None:
            orders = [step.order for step in self.sequence]
            if orders != list(range(1, len(orders) + 1)):
                raise ValueError("sequence orders must be 1, 2, 3, ... with no gaps")
        return self
