"""LLM opinion v1 (AI1, risk-v1 step 4): what AI1 hands to C3 for one evidence group.

One `GroupOpinion` per evidence group `(technique, entity)` of an incident, keyed exactly as C3's
risk code keys its groups (`app.correlation.risk`: technique = the dataset attack type or
"unknown", entity = `entity_of(event)`). C3's stacker reads `p_llm` (design note section 9A.2,
decision RV1-D2). Until a calibrator is fitted, `p_llm` is null and only `p_raw` is given.

This is AI1's own format, not a shared contract (C3 owns the contracts; the risk-side fields are
contracts 1.4, designed in step 6). Schema: contracts/ai1/llm-opinion-v1.schema.json.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

OPINION_FORMAT = "icd-llm-opinion-v1"

OpinionMethod = Literal["samples", "logprob"]
OpinionStatus = Literal["ok", "failed"]


class GroupOpinion(BaseModel):
    """The LLM's calibrated opinion that one evidence group is a real attack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["icd-llm-opinion-v1"] = Field(
        default=OPINION_FORMAT, description="File format and version."
    )
    incident_id: str | None = Field(
        default=None, description="Incident the group belongs to; null for a calibration group."
    )
    technique: str = Field(
        min_length=1, description="Group key, part 1: dataset attack type, or 'unknown'."
    )
    entity: str = Field(
        min_length=1,
        description="Group key, part 2: source-side entity as C3 computes it (real value; this "
        "record stays on the app host, the model only ever saw a masked token).",
    )
    event_count: int = Field(ge=1, description="Events in the group.")
    shown_event_ids: list[str] = Field(
        min_length=1, description="The events the model was shown (up to the view cap)."
    )
    status: OpinionStatus = Field(description="ok = p_raw is set; failed = no opinion.")
    failure: str | None = Field(
        default=None, description="Why there is no opinion (status failed only)."
    )
    method: OpinionMethod = Field(
        description="samples = share of 'yes' over n answers; logprob = token probability of 'yes'."
    )
    samples_requested: int = Field(ge=1, description="Answers asked for.")
    samples_valid: int = Field(ge=0, description="Answers that parsed as yes or no.")
    yes_count: int = Field(ge=0, description="Valid answers that said yes.")
    p_raw: float | None = Field(
        default=None, ge=0, le=1, description="Uncalibrated probability of 'real attack'."
    )
    p_llm: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Calibrated probability (Platt scaling); null when no calibrator was given "
        "or the opinion failed. This is the value C3's stacker reads.",
    )
    calibrator_version: str | None = Field(
        default=None, description="Calibrator that produced p_llm; null when p_llm is null."
    )
    reasons: list[str] = Field(
        default_factory=list, max_length=5, description="Short reasons the model gave (audit)."
    )
    prompt_version: str = Field(min_length=1, description="Opinion prompt version.")
    model_id: str = Field(min_length=1, description="Model pin (name, or name@revision).")
    temperature: float = Field(ge=0, description="Sampling temperature used.")
    cache_key: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="SHA-256 of the view, prompt, model and settings."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.status == "ok":
            if self.p_raw is None or self.failure is not None:
                raise ValueError("an ok opinion has p_raw and no failure")
        elif self.p_raw is not None or self.p_llm is not None or not self.failure:
            raise ValueError("a failed opinion has a failure and neither p_raw nor p_llm")
        if (self.p_llm is None) != (self.calibrator_version is None):
            raise ValueError("p_llm and calibrator_version are set together")
        if self.yes_count > self.samples_valid or self.samples_valid > self.samples_requested:
            raise ValueError("yes_count <= samples_valid <= samples_requested")
        if len(self.shown_event_ids) > self.event_count:
            raise ValueError("more shown events than events in the group")
        return self

    @property
    def key(self) -> tuple[str, str]:
        """The group key C3 joins on."""
        return (self.technique, self.entity)
