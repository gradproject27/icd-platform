"""AuditRecord: a security-relevant decision or action (FR-35, C-14, NFR-S-04, NFR-SF-07).

Records are append-only, so the model is immutable like every contract.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.common import Id, JsonScalar, NonEmptyStr, UtcDatetime, _Contract


class AuditEventType(StrEnum):
    """Audit event types (response spec section 11, auth doc; incident.* proposed by C3)."""

    STATUS_CHANGED = "status_changed"
    TRANSITION_REFUSED = "transition_refused"
    ANALYSIS_FAILED = "analysis.failed"
    RESPONSE_WINDOW_OPENED = "response_window.opened"
    RESPONSE_WINDOW_REMINDER = "response_window.reminder"
    DECISION_RECORDED = "decision.recorded"
    DECISION_REFUSED = "decision.refused"
    RESPONSE_WINDOW_EXPIRED = "response_window.expired"
    EXPIRY_DUPLICATE_IGNORED = "expiry_duplicate_ignored"
    SCENARIO_SELECTED = "scenario.selected"
    SCENARIO_NO_MATCH = "scenario.no_match"
    ACTION_SIMULATED = "action.simulated"
    ISOLATION_RELEASED = "isolation.released"
    NOTIFICATION_SENT = "notification.sent"
    AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOCKOUT = "auth.lockout"
    ACCESS_REFUSED = "access.refused"
    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"


SIMULATED_EVENT_TYPES = frozenset(
    {AuditEventType.ACTION_SIMULATED, AuditEventType.ISOLATION_RELEASED}
)
INCIDENT_SCOPED_EVENT_TYPES = frozenset(
    {
        AuditEventType.STATUS_CHANGED,
        AuditEventType.TRANSITION_REFUSED,
        AuditEventType.ANALYSIS_FAILED,
        AuditEventType.RESPONSE_WINDOW_OPENED,
        AuditEventType.RESPONSE_WINDOW_REMINDER,
        AuditEventType.RESPONSE_WINDOW_EXPIRED,
        AuditEventType.DECISION_RECORDED,
        AuditEventType.DECISION_REFUSED,
        AuditEventType.EXPIRY_DUPLICATE_IGNORED,
        AuditEventType.SCENARIO_SELECTED,
        AuditEventType.SCENARIO_NO_MATCH,
        AuditEventType.ACTION_SIMULATED,
        AuditEventType.ISOLATION_RELEASED,
        AuditEventType.INCIDENT_CREATED,
        AuditEventType.INCIDENT_UPDATED,
    }
)
NON_USER_ACTORS = frozenset({"system", "anonymous"})


class UserRole(StrEnum):
    """The four roles (D7.1)."""

    SOC_ANALYST = "soc_analyst"
    SOC_MANAGER = "soc_manager"
    SECURITY_ENGINEER = "security_engineer"
    SYSTEM_ADMINISTRATOR = "system_administrator"


class AuditResult(StrEnum):
    """Outcome of the audited operation."""

    SUCCESS = "success"
    FAILURE = "failure"
    REFUSED = "refused"
    IGNORED = "ignored"


class AuditRecord(_Contract):
    """A record of a security-relevant decision or action (FR-35, C-14, NFR-SF-07)."""

    schema_version: Literal["1.0"] = Field(default="1.0", description="Contract version.")
    record_id: Id = Field(description="Unique record ID.")
    occurred_at: UtcDatetime = Field(description="Database time (now()) when written, UTC.")
    event_type: AuditEventType = Field(description="What happened.")
    actor: NonEmptyStr = Field(
        description="User ID, system, or anonymous for a failed login with no known user."
    )
    actor_role: UserRole | None = Field(
        default=None, description="Role of the user; null for system and anonymous."
    )
    incident_id: Id | None = Field(
        default=None, description="Incident ID; null for records with no incident, such as login."
    )
    result: AuditResult = Field(description="Outcome of the operation.")
    simulated: bool = Field(
        default=False,
        description="True exactly for action.simulated and isolation.released (NFR-SF-07).",
    )
    details: dict[str, JsonScalar] = Field(
        default_factory=dict,
        description="For example previous and new state, scenario ID, window ID, reason. "
        "Never passwords, hashes or session tokens.",
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.simulated != (self.event_type in SIMULATED_EVENT_TYPES):
            raise ValueError(
                "simulated must be true for action.simulated and isolation.released only"
            )
        if self.event_type in INCIDENT_SCOPED_EVENT_TYPES and self.incident_id is None:
            raise ValueError(f"{self.event_type} requires incident_id")
        if (self.actor in NON_USER_ACTORS) != (self.actor_role is None):
            raise ValueError("actor_role must be null exactly when actor is system or anonymous")
        return self
