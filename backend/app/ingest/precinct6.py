"""Parser for dataset `precinct6`: WitFoo Precinct6 signal rows (risk-v1 step 3c).

Precinct6 ships Parquet (`signals/signals.parquet`, 2,011,674 rows, and
`signals/incident_signals.parquet`, 238,511 rows; dataset profile section 3.1). The upload
path takes text files, so a slice is first exported to JSON lines with
`python -m app.ingest.precinct6_export` (one row per line, the columns unchanged), and this
parser reads that file. Field rules: docs/ingestion.md section 11.

Role (RV1-D5, CON-20): an agreement check against WitFoo's own correlation engine, never ground
truth and never training data. The CON-20 columns (WitFoo's incident links, rules, scores,
dispositions, techniques) are dropped here: they never reach an Event field or extra_fields,
so correlation and the risk score cannot read WitFoo's answer.
"""

import json
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.contracts import Event, Provenance
from app.ingest import normalize as norm
from app.ingest.event_types import EventTypes
from app.ingest.interface import IntakeContext, ParseError, Quarantined
from app.ingest.labels import LabelMap, LabelProblem
from app.ingest.lines import Line, excerpt, read_lines

DATASET_ID = "precinct6"

# CON-20 columns (dataset profile section 4.1): derived by WitFoo's engine from the incident.
# label_binary is read only as the dataset label (EventLabel), never copied.
CON20 = frozenset(
    {
        "label_binary", "incident_ids", "matched_rules", "set_roles", "mo_name",
        "suspicion_score", "label_confidence", "lifecycle_stage", "disposition", "status_name",
        "disposition_category", "is_false_positive", "attack_techniques", "attack_tactics",
        "defense_techniques",
    }
)  # fmt: skip

# Columns mapped to Event fields; not copied to extra_fields unless unusable (<column>_raw).
MAPPED = frozenset(
    {
        "artifact_id", "timestamp", "src_host", "src_ip", "dst_ip", "src_port", "dst_port",
        "protocol", "username",
    }
)  # fmt: skip

MAX_TEXT = 4000


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    return norm.clean(str(value))


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def type_key(record: dict[str, Any]) -> str | None:
    return _text(record.get("message_type"))


class _Builder:
    def __init__(self, context: IntakeContext) -> None:
        self.context = context
        self.labels = LabelMap(DATASET_ID)
        self.types = EventTypes(DATASET_ID)

    def ref(self, number: int) -> str:
        return f"{self.context.source_file}:{number}"

    def quarantined(self, number: int, code: str, reason: str, raw: str | None) -> Quarantined:
        return Quarantined(
            record_ref=self.ref(number),
            reason_code=code,
            reason=reason,
            raw_excerpt=excerpt(raw) if raw is not None else None,
        )

    def record(self, line: Line) -> Event | Quarantined:
        if line.text is None:
            assert line.code is not None and line.reason is not None
            return self.quarantined(line.number, line.code, line.reason, line.excerpt)
        text = line.text
        if not text.strip():
            return self.quarantined(line.number, "empty_record", "the line is empty", None)
        try:
            record = json.loads(text)
        except ValueError as exc:
            return self.quarantined(line.number, "bad_json", f"not a JSON line: {exc}", text)
        if not isinstance(record, dict):
            reason = "the line is not a JSON object"
            return self.quarantined(line.number, "not_an_object", reason, text)
        artifact = _text(record.get("artifact_id"))
        if artifact is None:
            reason = "artifact_id (the record ID) is empty"
            return self.quarantined(line.number, "missing_record_id", reason, text)
        raw_time = _text(record.get("timestamp"))
        if raw_time is None:
            reason = "timestamp (event time) is empty"
            return self.quarantined(line.number, "missing_timestamp", reason, text)
        try:
            timestamp = norm.epoch_seconds(raw_time)
        except norm.BadValue as exc:
            return self.quarantined(line.number, "bad_timestamp", f"timestamp: {exc}", text)
        try:
            return self.event(line.number, record, artifact, timestamp)
        except LabelProblem as exc:
            return self.quarantined(line.number, exc.code, exc.reason, text)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "record"
            return self.quarantined(line.number, "invalid_event", f"{where}: {first['msg']}", text)

    def event(
        self, number: int, record: dict[str, Any], artifact: str, timestamp: datetime
    ) -> Event:
        extra: dict[str, Any] = {
            str(key): _scalar(value)
            for key, value in record.items()
            if key not in CON20 and key not in MAPPED
        }
        entities: dict[str, Any] = {}
        for column, field, convert in (
            ("src_ip", "src_ip", norm.ip_address),
            ("dst_ip", "dst_ip", norm.ip_address),
            ("src_port", "src_port", norm.port),
            ("dst_port", "dst_port", norm.port),
            ("protocol", "protocol", norm.iana_protocol),
        ):
            original = _text(record.get(column))
            value = convert(original)
            entities[field] = value
            if value is None and original is not None:
                extra[f"{column}_raw"] = norm.short(original, 100)

        label_raw = record.get("label_binary")
        label = self.labels.label(None if label_raw is None else str(label_raw), None)
        event_type = self.types.event_type(type_key(record))
        return Event(
            event_id=f"{DATASET_ID}:{norm.id_part(artifact, 100)}",
            timestamp=timestamp,
            ingested_at=self.context.ingested_at,
            event_type=event_type,
            label=label,
            host=_text(record.get("src_host")),
            user=_text(record.get("username")),
            privileged_user=None,
            summary=_summary(record),
            provenance=Provenance(
                dataset_id=self.context.dataset_id,
                source_file=self.context.source_file,
                record_ref=self.ref(number),
                source_format="json",
            ),
            extra_fields=extra,
            **entities,
        )


def _summary(record: dict[str, Any]) -> str:
    """A short description with no IP, host or user in it, so masking stays simple."""
    words = []
    for column, word in (
        ("stream_name", "stream"),
        ("message_type", "type"),
        ("product_name", "product"),
        ("action", "action"),
    ):
        value = _text(record.get(column))
        if value is not None:
            words.append(f"{word} {norm.short(value, 40)}")
    return "Precinct6 signal" + (": " + ", ".join(words) if words else "")


def parse_precinct6(path: Path, context: IntakeContext) -> Iterator[Event | Quarantined]:
    """Yield one Event or Quarantined per line, in file order."""
    if context.dataset_id != DATASET_ID:
        raise ParseError(f"The Precinct6 parser does not read dataset {context.dataset_id}.")
    if not path.is_file():
        raise ParseError("The stored file is missing.")
    with path.open("rb") as file:
        magic = file.read(4)
    if magic == b"PAR1":
        raise ParseError(
            "This is a Parquet file. Export a slice to JSON lines first: "
            "python -m app.ingest.precinct6_export <file.parquet> --out <slice.jsonl>"
        )
    builder = _Builder(context)
    for line in read_lines(path):
        yield builder.record(line)


def profile(path: Path) -> dict[str, Any]:
    """Aggregate-only profile of one exported Precinct6 JSON-lines file.

    Counts of label_binary, stream_name, message_type (with the event_type each maps to) and
    the columns present. It never outputs a host, user, IP, message or CON-20 value other than
    the label.
    """
    types = EventTypes(DATASET_ID)
    counters: dict[str, Counter[str]] = {
        name: Counter() for name in ("label_binary", "stream_name", "message_type")
    }
    columns: Counter[str] = Counter()
    lines = bad = 0
    for line in read_lines(path):
        lines += 1
        try:
            record = json.loads(line.text) if line.text is not None else None
        except ValueError:
            record = None
        if not isinstance(record, dict):
            bad += 1
            continue
        columns.update(record.keys())
        for name, counter in counters.items():
            counter[_text(record.get(name)) or "(empty)"] += 1
    return {
        "file": path.name,
        "lines": lines,
        "not_a_json_object": bad,
        "columns": dict(sorted(columns.items())),
        "label_binary": dict(counters["label_binary"]),
        "stream_name": dict(counters["stream_name"].most_common(100)),
        "message_type": {
            key: {"count": count, "event_type": types.event_type(key)}
            for key, count in counters["message_type"].most_common(100)
        },
    }
