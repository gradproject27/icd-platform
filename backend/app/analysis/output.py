"""LLM output v0: the JSON object the model must return (AI1).

It is richer than AnalysisReport: every claim carries its citations and the entities it names,
so the grounding check can verify it. `mapper.to_report` turns it into AnalysisReport 1.0.
The model never returns a risk score (OD-04) or the confidence (OD-16).
null in a section means "not determined", as in the contracts.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts import FindingCategory
from app.contracts.common import Id, NonEmptyStr

OUTPUT_VERSION = "ai1-output-0.1"

Fraction = Annotated[float, Field(ge=0, le=1)]


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnalysisOutcome(StrEnum):
    """The model's own verdict on whether the evidence allows an analysis."""

    COMPLETE = "complete"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Entities(_Output):
    """Every host, IP and user named in the claim text, written exactly as in the package."""

    hosts: list[NonEmptyStr] = Field(default_factory=list, description="Host values or tokens.")
    ips: list[NonEmptyStr] = Field(default_factory=list, description="IP values or tokens.")
    users: list[NonEmptyStr] = Field(default_factory=list, description="User values or tokens.")

    def values(self) -> set[str]:
        return {*self.hosts, *self.ips, *self.users}


class Claim(_Output):
    """One statement with its support (FR-15)."""

    text: NonEmptyStr = Field(description="The statement.")
    category: FindingCategory = Field(
        description="evidence_supported, likely_interpretation or hypothesis."
    )
    cited_event_ids: list[Id] = Field(
        default_factory=list,
        description="Event IDs from the package. At least one unless the claim is a hypothesis.",
    )
    entities: Entities = Field(default_factory=Entities, description="Entities named in the text.")

    @model_validator(mode="after")
    def _factual_claims_cite(self) -> Self:
        if self.category != FindingCategory.HYPOTHESIS and not self.cited_event_ids:
            raise ValueError(f"a {self.category.value} claim must cite at least one event")
        if len(set(self.cited_event_ids)) != len(self.cited_event_ids):
            raise ValueError("cited_event_ids must not repeat")
        return self


class AttackType(_Output):
    """Suspected attack type and the claim behind it."""

    category: NonEmptyStr = Field(description="Short attack type, for example brute_force.")
    claim: Claim = Field(description="Why this type fits the events.")


class Recommendation(_Output):
    """Advice for the analyst. Never an executed or automatic action (C-10, NFR-SF-02)."""

    action: NonEmptyStr = Field(description="What the analyst could do.")
    rationale: NonEmptyStr = Field(description="Why, in terms of the cited events.")
    cited_event_ids: list[Id] = Field(min_length=1, description="Events behind the advice.")
    reversible_alternative: NonEmptyStr | None = Field(
        default=None, description="A less disruptive option; null if none."
    )


class Uncertainty(_Output):
    """Something the evidence does not show, and what would settle it."""

    statement: NonEmptyStr = Field(description="What is not known.")
    missing_evidence: NonEmptyStr = Field(description="Which logs or fields would settle it.")


class LlmOutput(_Output):
    """The model's answer for one incident (prompt v0)."""

    output_version: Literal["ai1-output-0.1"] = Field(description="Output format version.")
    incident_id: Id = Field(description="Copied from the package.")
    analysis_status: AnalysisOutcome = Field(
        description="insufficient_evidence when the events are too thin to assess the incident."
    )
    summary: Claim = Field(description="Concise summary (FR-14).")
    attack_type: AttackType | None = Field(default=None, description="null = not determined.")
    sequence: Annotated[list[Claim], Field(min_length=1)] | None = Field(
        default=None, description="Ordered steps; null = not determined."
    )
    findings: list[Claim] = Field(description="Suspicious behaviour; [] when there is none.")
    weaknesses: Annotated[list[Claim], Field(min_length=1)] | None = Field(
        default=None, description="Only when events show them; null = not determined."
    )
    impact: Claim | None = Field(default=None, description="null = not determined.")
    recommendations: list[Recommendation] = Field(description="Advice; [] allowed.")
    risk_justification: Claim | None = Field(
        default=None,
        description="Explains the given deterministic risk score; never a new score.",
    )
    uncertainties: list[Uncertainty] = Field(min_length=1, description="At least one.")
    limitations: list[NonEmptyStr] = Field(min_length=1, description="Limits of this analysis.")
    self_rating: Fraction | None = Field(
        default=None, description="The model's own rating 0 to 1. Stored, never gates (OD-16)."
    )

    @model_validator(mode="after")
    def _sequence_steps_cite(self) -> Self:
        for step in self.sequence or []:
            if not step.cited_event_ids:
                raise ValueError("every sequence step must cite at least one event")
        return self

    def claims(self) -> list[tuple[str, Claim]]:
        """Every claim with its location, for the grounding check."""
        found: list[tuple[str, Claim]] = [("summary", self.summary)]
        if self.attack_type is not None:
            found.append(("attack_type", self.attack_type.claim))
        found += [(f"sequence[{i}]", c) for i, c in enumerate(self.sequence or [])]
        found += [(f"findings[{i}]", c) for i, c in enumerate(self.findings)]
        found += [(f"weaknesses[{i}]", c) for i, c in enumerate(self.weaknesses or [])]
        if self.impact is not None:
            found.append(("impact", self.impact))
        if self.risk_justification is not None:
            found.append(("risk_justification", self.risk_justification))
        return found

    def texts(self) -> list[tuple[str, str]]:
        """Every free-text field a reader sees, with its location."""
        found = [(f"{loc}.text", claim.text) for loc, claim in self.claims()]
        if self.attack_type is not None:
            found.append(("attack_type.category", self.attack_type.category))
        for i, rec in enumerate(self.recommendations):
            found.append((f"recommendations[{i}].action", rec.action))
            found.append((f"recommendations[{i}].rationale", rec.rationale))
            if rec.reversible_alternative:
                found.append(
                    (f"recommendations[{i}].reversible_alternative", rec.reversible_alternative)
                )
        for i, unc in enumerate(self.uncertainties):
            found.append((f"uncertainties[{i}].statement", unc.statement))
            found.append((f"uncertainties[{i}].missing_evidence", unc.missing_evidence))
        found += [(f"limitations[{i}]", text) for i, text in enumerate(self.limitations)]
        return found
