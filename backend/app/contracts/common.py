"""Shared base class, types and enums used by more than one contract."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, StringConstraints

SCHEMA_VERSION = "1.0"

Id = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
JsonScalar = str | int | float | bool | None


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


# A timezone is required; the value is stored and serialized as UTC.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LabelStatus(StrEnum):
    """Dataset label of an event. A missing label is unlabelled, never inferred (OD-21)."""

    FLAGGED = "flagged"
    UNFLAGGED = "unflagged"
    UNLABELLED = "unlabelled"


class EventRole(StrEnum):
    """Why an event belongs to an incident. Context events are never treated as malicious."""

    FLAGGED = "flagged"
    CONTEXT = "context"


class RiskLevel(StrEnum):
    """Risk level derived from the score by C3's configurable thresholds (FR-20)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
