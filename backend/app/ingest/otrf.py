"""Parser for dataset `otrf`: Windows event logs from OTRF Security Datasets (risk-v1 step 3b).

Input is the JSON-lines member of an OTRF zip, one Windows event per line: APT29 day 1 and day
2 (`apt29_evals_day*_manual_*.json`) and the atomic sets (for example
`psh_lsass_memory_dump_comsvcs_*.json`). The Zeek logs are a different format and are not read
here. Field rules: docs/ingestion.md section 10.

OTRF has no per-event label: the ATT&CK technique is dataset metadata (label-mapping.json,
label_scope per_dataset; attack_maps/otrf.toml), so every event is unlabelled and nothing in
an event hints at the technique.

Event time. Sysmon events carry `UtcTime` (UTC by definition). Other events carry only a local
time without a zone (`EventTime`, or `TimeCreated` in some atomic sets). The parser reads the
file once first and measures local minus UtcTime on every event that has both, rounded to 15
minutes. If every such event gives the same offset, it converts the local times with it;
otherwise (or with no such event) the zone is unknown and an event without `UtcTime` is
quarantined (`unknown_time_zone`), never guessed. Measured on 25 Nov 2026: -240 minutes in APT29
day 1 (143,883 of 143,883 pairs) and the SMB atomic set (412 of 412); -960 minutes in the LSASS
atomic set (148 of 148), whose `TimeCreated` is a 12-hour clock without AM or PM.
"""

import json
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.contracts import Event, Provenance
from app.ingest import normalize as norm
from app.ingest.event_types import EventTypes
from app.ingest.interface import IntakeContext, ParseError, Quarantined
from app.ingest.labels import LabelMap, LabelProblem
from app.ingest.lines import Line, excerpt, read_lines

DATASET_ID = "otrf"

LOCAL_TIME_FIELDS = ("EventTime", "TimeCreated")
OFFSET_STEP_MINUTES = 15

# Source fields mapped to Event entity fields, in order of preference. They are not copied to
# extra_fields unless the value could not be used (then <field>_raw keeps it).
HOST_FIELDS = ("Hostname",)
SRC_IP_FIELDS = ("SourceAddress", "SourceIp")
DST_IP_FIELDS = ("DestAddress", "DestinationIp")
SRC_PORT_FIELDS = ("SourcePort",)
DST_PORT_FIELDS = ("DestPort", "DestinationPort")
PROTOCOL_FIELDS = ("Protocol",)
ENTITY_FIELDS = frozenset(
    HOST_FIELDS + SRC_IP_FIELDS + DST_IP_FIELDS + SRC_PORT_FIELDS + DST_PORT_FIELDS
    + PROTOCOL_FIELDS
)  # fmt: skip

# Which account field is "the" user depends on the event. Logon events name the account that
# logged on in TargetUserName; most other Security events name the acting account in
# SubjectUserName; Sysmon writes DOMAIN\\user in User. All account fields stay in extra_fields.
TARGET_USER_EVENTS = frozenset({4624, 4625, 4634, 4647, 4648, 4768, 4769, 4776})
USER_FIELDS = ("SubjectUserName", "User")
# 4672 "Special privileges assigned to new logon": the data itself says the account is
# privileged. Every other event leaves privileged_user null (the data does not say).
PRIVILEGED_LOGON_EVENT = 4672

MAX_TEXT = 4000  # longest string kept in extra_fields (script blocks can be much longer)


class _NoTime(ValueError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _naive_time(value: Any, field: str) -> datetime:
    """A zone-less "YYYY-MM-DD HH:MM:SS[.fff]" value as a naive datetime, else _NoTime."""
    if not isinstance(value, str) or not value.strip():
        raise _NoTime("missing_timestamp", f"{field} is empty")
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise _NoTime("bad_timestamp", f"{field} {value[:40]!r} is not a date and time") from exc
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment


def _in_range(moment: datetime, field: str) -> datetime:
    aware = moment.replace(tzinfo=UTC)
    if not norm.EARLIEST <= aware < norm.LATEST:
        raise _NoTime("bad_timestamp", f"{field} {aware.isoformat()} is outside 1990 to 2100")
    return aware


def _local_field(record: dict[str, Any]) -> str | None:
    return next((name for name in LOCAL_TIME_FIELDS if name in record), None)


def _pair_offset(record: dict[str, Any]) -> int | None:
    """Local minus UtcTime in minutes, rounded to 15, for an event that has both; else None."""
    local = _local_field(record)
    if "UtcTime" not in record or local is None:
        return None
    try:
        utc = _naive_time(record["UtcTime"], "UtcTime")
        here = _naive_time(record[local], local)
    except _NoTime:
        return None
    minutes = (here - utc).total_seconds() / 60
    return int(round(minutes / OFFSET_STEP_MINUTES) * OFFSET_STEP_MINUTES)


def _decode(text: str) -> dict[str, Any] | None:
    try:
        record = json.loads(text)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def measure_offsets(path: Path) -> Counter[int]:
    """First pass: how often each local-minus-UTC offset (minutes) occurs in the file."""
    offsets: Counter[int] = Counter()
    for line in read_lines(path):
        if line.text is None or '"UtcTime"' not in line.text:
            continue
        record = _decode(line.text)
        if record is not None and (offset := _pair_offset(record)) is not None:
            offsets[offset] += 1
    return offsets


def file_offset(offsets: Counter[int]) -> int | None:
    """The one offset every paired event agrees on, else None (zone unknown)."""
    return next(iter(offsets)) if len(offsets) == 1 else None


def type_key(record: dict[str, Any]) -> str | None:
    """The event-types.json key: "<channel, lower case>:<EventID>"."""
    channel, event_id = record.get("Channel"), record.get("EventID")
    if not isinstance(channel, str) or not channel.strip() or isinstance(event_id, bool):
        return None
    if isinstance(event_id, str) and event_id.strip().isdigit():
        event_id = int(event_id)
    if not isinstance(event_id, int):
        return None
    return f"{channel.strip().lower()}:{event_id}"


def _event_number(record: dict[str, Any]) -> int | None:
    value = record.get("EventID")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _scalar(value: Any) -> Any:
    """A JSON value for extra_fields: scalars kept (long text cut), lists and objects as JSON."""
    if value is None or isinstance(value, bool | int | float):
        return value
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    return norm.clean(str(value))


class _Builder:
    def __init__(self, context: IntakeContext, offset: int | None) -> None:
        self.context = context
        self.offset = offset
        self.labels = LabelMap(DATASET_ID)
        self.types = EventTypes(DATASET_ID)
        self.stem = norm.id_part(Path(context.source_file).stem)

    def ref(self, number: int) -> str:
        return f"{self.context.source_file}:{number}"

    def quarantined(self, number: int, code: str, reason: str, raw: str | None) -> Quarantined:
        return Quarantined(
            record_ref=self.ref(number),
            reason_code=code,
            reason=reason,
            raw_excerpt=excerpt(raw) if raw is not None else None,
        )

    def time(self, record: dict[str, Any]) -> tuple[datetime, str]:
        if "UtcTime" in record:
            return _in_range(_naive_time(record["UtcTime"], "UtcTime"), "UtcTime"), "UtcTime"
        local = _local_field(record)
        if local is None:
            raise _NoTime("missing_timestamp", "no UtcTime, EventTime or TimeCreated")
        moment = _naive_time(record[local], local)
        if self.offset is None:
            raise _NoTime(
                "unknown_time_zone",
                f"only {local} (local time, no zone) and the file gives no single offset to UTC",
            )
        return _in_range(moment - timedelta(minutes=self.offset), local), local

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
        try:
            timestamp, source = self.time(record)
        except _NoTime as exc:
            return self.quarantined(line.number, exc.code, exc.reason, text)
        try:
            return self.event(line.number, record, timestamp, source)
        except LabelProblem as exc:
            return self.quarantined(line.number, exc.code, exc.reason, text)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "record"
            return self.quarantined(line.number, "invalid_event", f"{where}: {first['msg']}", text)

    def event(
        self, number: int, record: dict[str, Any], timestamp: datetime, time_source: str
    ) -> Event:
        extra: dict[str, Any] = {
            str(key): _scalar(value) for key, value in record.items() if key not in ENTITY_FIELDS
        }
        extra["timestamp_source"] = time_source
        if time_source != "UtcTime":
            extra["utc_offset_minutes"] = self.offset

        def pick(fields: tuple[str, ...], convert: Any) -> Any:
            for field in fields:
                if field not in record:
                    continue
                original = _text(record[field])
                value = convert(original)
                if value is None and original is not None:
                    extra[f"{field}_raw"] = norm.short(original, 100)
                if value is not None:
                    return value
            return None

        event_number = _event_number(record)
        user_fields = (
            ("TargetUserName", *USER_FIELDS) if event_number in TARGET_USER_EVENTS else USER_FIELDS
        )
        user = next(
            (text for field in user_fields if (text := _text(record.get(field))) is not None),
            None,
        )
        label = self.labels.label(None)
        return Event(
            event_id=f"{DATASET_ID}:{self.stem}:{number}",
            timestamp=timestamp,
            ingested_at=self.context.ingested_at,
            event_type=self.types.event_type(type_key(record)),
            label=label,
            host=pick(HOST_FIELDS, lambda text: text),
            src_ip=pick(SRC_IP_FIELDS, norm.ip_address),
            dst_ip=pick(DST_IP_FIELDS, norm.ip_address),
            src_port=pick(SRC_PORT_FIELDS, norm.port),
            dst_port=pick(DST_PORT_FIELDS, norm.port),
            protocol=pick(PROTOCOL_FIELDS, norm.iana_protocol),
            user=user,
            privileged_user=True if event_number == PRIVILEGED_LOGON_EVENT else None,
            summary=_summary(record, self.types.event_type(type_key(record))),
            provenance=Provenance(
                dataset_id=self.context.dataset_id,
                source_file=self.context.source_file,
                record_ref=self.ref(number),
                source_format="json",
            ),
            extra_fields=extra,
        )


def _program(value: Any) -> str | None:
    """File name of a program path, without the folders (which can hold a user name)."""
    text = _text(value)
    if text is None:
        return None
    name = text.replace("/", "\\").rsplit("\\", 1)[-1]
    return norm.short(name, 40) if name else None


def _summary(record: dict[str, Any], event_type: str) -> str:
    """A short description with no IP, host or user in it, so masking stays simple."""
    channel = _text(record.get("Channel")) or "unknown channel"
    words = [f"{event_type.replace('_', ' ')} ({norm.short(channel, 60)} {record.get('EventID')})"]
    program = next(
        (
            name
            for field in ("Image", "NewProcessName", "ProcessName", "Application")
            if (name := _program(record.get(field))) is not None
        ),
        None,
    )
    if program is not None:
        words.append(f"program {program}")
    return ", ".join(words)


def parse_otrf(path: Path, context: IntakeContext) -> Iterator[Event | Quarantined]:
    """Yield one Event or Quarantined per line, in file order (after the offset pass)."""
    if context.dataset_id != DATASET_ID:
        raise ParseError(f"The OTRF parser does not read dataset {context.dataset_id}.")
    if not path.is_file():
        raise ParseError("The stored file is missing.")
    builder = _Builder(context, file_offset(measure_offsets(path)))
    for line in read_lines(path):
        yield builder.record(line)


def profile(path: Path) -> dict[str, Any]:
    """Aggregate-only profile of one OTRF JSON-lines file.

    Counts of Channel:EventID keys (with the event_type each maps to), time fields and the
    local-minus-UTC offsets. It never outputs a host, user, IP or message.
    """
    types = EventTypes(DATASET_ID)
    keys: Counter[str] = Counter()
    time_fields: Counter[str] = Counter()
    lines = bad = 0
    for line in read_lines(path):
        lines += 1
        record = _decode(line.text) if line.text is not None else None
        if record is None:
            bad += 1
            continue
        keys[type_key(record) or "(none)"] += 1
        for name in ("UtcTime", *LOCAL_TIME_FIELDS, "@timestamp"):
            if name in record:
                time_fields[name] += 1
    offsets = measure_offsets(path)
    return {
        "file": path.name,
        "lines": lines,
        "not_a_json_object": bad,
        "time_fields": dict(time_fields),
        "utc_offset_minutes_measured": {str(k): v for k, v in sorted(offsets.items())},
        "utc_offset_minutes_used": file_offset(offsets),
        "event_types": {
            key: {"count": count, "event_type": types.event_type(key)}
            for key, count in keys.most_common(80)
        },
        "unmapped_events": sum(
            count for key, count in keys.items() if types.event_type(key) == "unknown"
        ),
    }
