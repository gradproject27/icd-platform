"""Label handling from contracts/label-mapping.json (plan section 5, step 4; OD-21, FR-41).

The label comes only from the record's label column, matched exactly against the mapping.
No label means unlabelled. A value the mapping does not list, or lists as pending, is never
guessed: the record is quarantined with the reason (mapping rules unknown_value and
pending_values).
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

from app.contracts import EventLabel, LabelStatus

MAPPINGS_DIR = Path(__file__).resolve().parent / "mappings"
LABEL_MAPPING = MAPPINGS_DIR / "label-mapping.json"
"""Copy of contracts/label-mapping.json inside the app, because the Docker image only holds
backend/app. tests/ingest/test_packaged_data.py fails when the two differ."""


class LabelProblem(ValueError):
    """The label value cannot be mapped. code is the quarantine reason code."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@cache
def _mapping() -> dict[str, Any]:
    return json.loads(LABEL_MAPPING.read_text(encoding="utf-8"))


class LabelMap:
    """The mapped label values of one dataset."""

    def __init__(self, dataset_id: str, mapping: dict[str, Any] | None = None) -> None:
        mapping = mapping if mapping is not None else _mapping()
        sources = {source["dataset_id"]: source for source in mapping["sources"]}
        if dataset_id not in sources:
            raise KeyError(f"{dataset_id} is not a source in the label mapping")
        self.dataset_id = dataset_id
        self.version = mapping["mapping_version"]
        self.status: dict[str, LabelStatus | None] = {
            value["raw_value"]: LabelStatus(value["status"]) if value["status"] else None
            for value in sources[dataset_id].get("values", [])
        }

    def label(self, raw_value: str | None, attack_type: str | None = None) -> EventLabel:
        """EventLabel for one record, or LabelProblem. raw_value is matched exactly."""
        if raw_value is None or raw_value == "":
            return EventLabel(status=LabelStatus.UNLABELLED, attack_type=attack_type)
        shown = raw_value if len(raw_value) <= 40 else raw_value[:39] + "…"
        if raw_value not in self.status:
            raise LabelProblem(
                "unknown_label",
                f"label {shown!r} is not in label-mapping.json for {self.dataset_id}",
            )
        status = self.status[raw_value]
        if status is None:
            raise LabelProblem(
                "pending_label",
                f"label {shown!r} is listed but its mapping is pending a team decision",
            )
        return EventLabel(status=status, raw_value=raw_value, attack_type=attack_type)
