"""Event: one normalized security event, built by C2 (FR-02, FR-04, FR-05, FR-40, FR-41)."""

from typing import Annotated, Literal, Self

from pydantic import Field, IPvAnyAddress, StringConstraints, model_validator

from app.contracts.common import (
    Id,
    JsonScalar,
    LabelStatus,
    NonEmptyStr,
    UtcDatetime,
    _Contract,
)

Port = Annotated[int, Field(ge=0, le=65535)]
Summary = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class EventLabel(_Contract):
    """The dataset label of an event (OD-21, FR-41). The system never generates labels."""

    status: LabelStatus = Field(
        description="flagged, unflagged or unlabelled. unlabelled exactly when raw_value is null."
    )
    raw_value: NonEmptyStr | None = Field(
        default=None,
        description="The label exactly as in the dataset; null only when the record had none.",
    )
    attack_type: NonEmptyStr | None = Field(
        default=None, description="The dataset's attack-type column, kept as an attribute."
    )
    origin: Literal["dataset"] = Field(
        default="dataset", description="Always dataset: labels come only from the data (FR-41)."
    )

    @model_validator(mode="after")
    def _unlabelled_iff_no_raw_value(self) -> Self:
        if (self.status == LabelStatus.UNLABELLED) != (self.raw_value is None):
            raise ValueError("status must be unlabelled exactly when raw_value is null")
        return self


class Provenance(_Contract):
    """Where the event came from (FR-05)."""

    dataset_id: Id = Field(description="ID of the uploaded dataset.")
    source_file: NonEmptyStr = Field(description="Name of the source file.")
    record_ref: NonEmptyStr = Field(
        description="Row number, line number or original record ID in the source file."
    )
    source_format: NonEmptyStr = Field(description="Format of the source, for example csv.")


class Event(_Contract):
    """One normalized security event (FR-02, FR-04, FR-05, FR-40, FR-41, OD-21, TD-12)."""

    schema_version: Literal["1.0"] = Field(default="1.0", description="Contract version.")
    event_id: Id = Field(
        description="Unique and stable across re-ingestion of the same record. "
        "A record without one is rejected by C2 (FR-03)."
    )
    timestamp: UtcDatetime = Field(
        description="When the activity happened (event time), UTC. "
        "A record without one is rejected by C2 (FR-03)."
    )
    ingested_at: UtcDatetime = Field(description="When the record was parsed (TD-12), UTC.")
    event_type: NonEmptyStr = Field(
        description="Normalized type from C2's vocabulary; unknown when it cannot be mapped."
    )
    label: EventLabel = Field(description="Dataset label (OD-21).")
    host: NonEmptyStr | None = Field(
        default=None, description="Host the event was observed on or is about; null if absent."
    )
    src_ip: IPvAnyAddress | None = Field(default=None, description="Source IP; null if absent.")
    dst_ip: IPvAnyAddress | None = Field(
        default=None, description="Destination IP; null if absent."
    )
    src_port: Port | None = Field(default=None, description="Source port; null if absent.")
    dst_port: Port | None = Field(default=None, description="Destination port; null if absent.")
    protocol: NonEmptyStr | None = Field(default=None, description="Protocol; null if absent.")
    user: NonEmptyStr | None = Field(
        default=None, description="Account name as in the source; null if absent."
    )
    privileged_user: bool | None = Field(
        default=None,
        description="Whether the account is privileged; null when the data does not say (OD-04).",
    )
    summary: Summary = Field(description="Short human-readable description built by C2.")
    provenance: Provenance = Field(description="Source of the record (FR-05).")
    extra_fields: dict[str, JsonScalar] = Field(
        default_factory=dict,
        description="Source fields that were not mapped (FR-02). Never columns listed in CON-20.",
    )
