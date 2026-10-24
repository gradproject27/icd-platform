"""ResponseAction: a proposed or simulated response action (FR-23, FR-27, FR-44, NFR-SF-01).

No real system is ever touched: simulated is always true.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.common import Id, JsonScalar, NonEmptyStr, UtcDatetime, _Contract


class ScenarioId(StrEnum):
    """Simulated response catalogue v0 (OD-20). Anything else is rejected (FR-44)."""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


class ActionState(StrEnum):
    """State of the action (response spec section 12, written there with hyphens)."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    SIMULATED_SUCCEEDED = "simulated_succeeded"
    SIMULATED_FAILED = "simulated_failed"


class ActionTrigger(StrEnum):
    """What caused the action to be decided."""

    ANALYST_DECISION = "analyst_decision"
    WINDOW_EXPIRY = "window_expiry"


class ActionTarget(_Contract):
    """Target of the simulated action (response spec section 9)."""

    host: NonEmptyStr | None = Field(default=None, description="Target host; every scenario.")
    ip: NonEmptyStr | None = Field(default=None, description="Source IP to block; S2.")
    account: NonEmptyStr | None = Field(default=None, description="Account to disable; S3.")


class ResponseAction(_Contract):
    """A proposed or simulated response action (FR-23, FR-27, FR-28, FR-44, FR-45, OD-20)."""

    schema_version: Literal["1.0"] = Field(default="1.0", description="Contract version.")
    action_id: Id = Field(description="Unique action ID.")
    incident_id: Id = Field(description="ID of the incident.")
    scenario_id: ScenarioId = Field(description="Catalogue v0 scenario, S1 to S4 (OD-20).")
    state: ActionState = Field(description="Action state.")
    trigger: ActionTrigger | None = Field(
        default=None,
        description="Analyst decision or window expiry; null while proposed, because nobody "
        "knows yet which will decide.",
    )
    decided_by: NonEmptyStr | None = Field(
        default=None, description="User ID, or system; null while proposed."
    )
    window_id: Id | None = Field(
        default=None, description="Response window the action came from, if any."
    )
    target: ActionTarget = Field(description="Target host, IP and account.")
    parameters: dict[str, JsonScalar] = Field(
        default_factory=dict, description="Scenario parameters, for example block_ip."
    )
    proposed_at: UtcDatetime = Field(description="When the action was proposed, UTC.")
    decided_at: UtcDatetime | None = Field(
        default=None, description="When it was decided, UTC; null while proposed."
    )
    executed_at: UtcDatetime | None = Field(
        default=None, description="When it was simulated, UTC; null until simulated."
    )
    failure_reason: NonEmptyStr | None = Field(
        default=None, description="Why the simulation failed; only for simulated_failed."
    )
    comment: NonEmptyStr | None = Field(
        default=None, description="Optional analyst comment (FR-28)."
    )
    simulated: Literal[True] = Field(
        default=True, description="Always true. No real system is touched (NFR-SF-01)."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.target.host is None:
            raise ValueError("target.host is required for every scenario")
        if self.scenario_id == ScenarioId.S2 and self.target.ip is None:
            raise ValueError("S2 requires target.ip")
        if self.scenario_id == ScenarioId.S3 and self.target.account is None:
            raise ValueError("S3 requires target.account")
        decision = (self.trigger, self.decided_by, self.decided_at)
        if self.state == ActionState.PROPOSED:
            if any(value is not None for value in decision):
                raise ValueError(
                    "a proposed action requires trigger, decided_by and decided_at to be null"
                )
        elif any(value is None for value in decision):
            raise ValueError("a decided action requires trigger, decided_by and decided_at")
        if self.trigger == ActionTrigger.WINDOW_EXPIRY and self.decided_by != "system":
            raise ValueError("window_expiry requires decided_by to be system")
        simulated_states = (ActionState.SIMULATED_SUCCEEDED, ActionState.SIMULATED_FAILED)
        if self.state in simulated_states and self.executed_at is None:
            raise ValueError("a simulated action requires executed_at")
        if (self.state == ActionState.SIMULATED_FAILED) != (self.failure_reason is not None):
            raise ValueError("failure_reason is required for simulated_failed and only then")
        present = (self.proposed_at, self.decided_at, self.executed_at)
        times = [t for t in present if t is not None]
        if times != sorted(times):
            raise ValueError("proposed_at <= decided_at <= executed_at must hold")
        return self
