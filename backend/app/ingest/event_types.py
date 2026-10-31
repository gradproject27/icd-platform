"""C2's event_type vocabulary from contracts/event-types.json (contracts v1 open question 1).

The type comes only from an activity field of the record, never from its label, so the
label cannot leak into correlation through event_type.
"""

import json
from functools import cache
from typing import Any

from app.ingest.labels import MAPPINGS_DIR

EVENT_TYPES = MAPPINGS_DIR / "event-types.json"
"""Copy of contracts/event-types.json; tests/ingest/test_packaged_data.py keeps them equal."""

UNKNOWN = "unknown"


@cache
def _vocabulary() -> dict[str, Any]:
    return json.loads(EVENT_TYPES.read_text(encoding="utf-8"))


def type_names() -> frozenset[str]:
    return frozenset(entry["name"] for entry in _vocabulary()["types"])


class EventTypes:
    """The event_type map of one dataset."""

    def __init__(self, dataset_id: str) -> None:
        sources = {source["dataset_id"]: source for source in _vocabulary()["sources"]}
        self.field: str = sources[dataset_id]["field"]
        self.map: dict[str, str] = sources[dataset_id]["map"]

    def event_type(self, value: str | None) -> str:
        if value is None:
            return UNKNOWN
        return self.map.get(value.strip().lower(), UNKNOWN)
