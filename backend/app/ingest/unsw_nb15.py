"""Parser for dataset `unsw-nb15`: the four headerless flow CSVs UNSW-NB15_1.csv to _4.csv.

One line is one flow record. Column names and meanings come from NUSW-NB15_features.csv
(docs/ingestion.md section 3). Every line read becomes an Event or a Quarantined record with
its reason, in file order; one bad line never stops the file (docs/api-upload-jobs.md
section 5).
"""

import csv
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

DATASET_ID = "unsw-nb15"

# The 49 columns in file order, as in NUSW-NB15_features.csv. The features file spells
# column 44 "ct_src_ ltm" (with a space); the space is dropped here.
COLUMNS = (
    "srcip", "sport", "dstip", "dsport", "proto", "state", "dur", "sbytes", "dbytes",
    "sttl", "dttl", "sloss", "dloss", "service", "Sload", "Dload", "Spkts", "Dpkts",
    "swin", "dwin", "stcpb", "dtcpb", "smeansz", "dmeansz", "trans_depth", "res_bdy_len",
    "Sjit", "Djit", "Stime", "Ltime", "Sintpkt", "Dintpkt", "tcprtt", "synack", "ackdat",
    "is_sm_ips_ports", "ct_state_ttl", "ct_flw_http_mthd", "is_ftp_login", "ct_ftp_cmd",
    "ct_srv_src", "ct_srv_dst", "ct_dst_ltm", "ct_src_ltm", "ct_src_dport_ltm",
    "ct_dst_sport_ltm", "ct_dst_src_ltm", "attack_cat", "Label",
)  # fmt: skip

# Mapped to Event fields. Label and attack_cat only ever reach EventLabel, never
# extra_fields, so correlation cannot read the label from a side field.
MAPPED = frozenset({"srcip", "sport", "dstip", "dsport", "proto", "Stime", "attack_cat", "Label"})
EXTRA = tuple(name for name in COLUMNS if name not in MAPPED)


def _is_header(fields: list[str]) -> bool:
    return bool(fields) and fields[0].strip().lower() == "srcip"


def _split(text: str) -> list[str]:
    return next(csv.reader([text]), [])


class _Builder:
    def __init__(self, context: IntakeContext) -> None:
        self.context = context
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

    def record(self, line: Line) -> Event | Quarantined | None:
        """Event or Quarantined for one line; None for a header line (not a record)."""
        if line.text is None:
            assert line.code is not None and line.reason is not None
            return self.quarantined(line.number, line.code, line.reason, line.excerpt)
        text = line.text
        if not text.strip():
            return self.quarantined(line.number, "empty_record", "the line is empty", None)
        try:
            fields = _split(text)
        except csv.Error as exc:
            return self.quarantined(line.number, "bad_csv", f"not a CSV line: {exc}", text)
        if line.number == 1 and _is_header(fields):
            return None
        if len(fields) != len(COLUMNS):
            return self.quarantined(
                line.number,
                "wrong_column_count",
                f"{len(fields)} columns, expected {len(COLUMNS)}",
                text,
            )
        row = dict(zip(COLUMNS, fields, strict=True))
        if norm.clean(row["Stime"]) is None:
            return self.quarantined(
                line.number, "missing_timestamp", "Stime (event time) is empty", text
            )
        try:
            timestamp = norm.epoch_seconds(row["Stime"])
        except norm.BadValue as exc:
            return self.quarantined(line.number, "bad_timestamp", f"Stime: {exc}", text)
        try:
            return self.event(line.number, row, timestamp)
        except LabelProblem as exc:
            return self.quarantined(line.number, exc.code, exc.reason, text)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "record"
            return self.quarantined(line.number, "invalid_event", f"{where}: {first['msg']}", text)

    def event(self, number: int, row: dict[str, str], timestamp: datetime) -> Event:
        extra: dict[str, Any] = {name: norm.scalar(row[name]) for name in EXTRA}
        entities: dict[str, Any] = {}
        for column, field, convert in (
            ("srcip", "src_ip", norm.ip_address),
            ("dstip", "dst_ip", norm.ip_address),
            ("sport", "src_port", norm.port),
            ("dsport", "dst_port", norm.port),
        ):
            value = convert(row[column])
            entities[field] = value
            original = norm.clean(row[column])
            if value is None and original is not None:
                extra[f"{column}_raw"] = norm.short(original, 100)

        attack_type = row["attack_cat"].strip() or None
        label = self.labels.label(row["Label"], attack_type)
        return Event(
            event_id=f"{self.context.dataset_id}:{self.stem}:{number}",
            timestamp=timestamp,
            ingested_at=self.context.ingested_at,
            event_type=self.types.event_type(row[self.types.field]),
            label=label,
            host=None,
            protocol=norm.protocol(row["proto"]),
            user=None,
            privileged_user=None,
            summary=_summary(row),
            provenance=Provenance(
                dataset_id=self.context.dataset_id,
                source_file=self.context.source_file,
                record_ref=self.ref(number),
                source_format="csv",
            ),
            extra_fields=extra,
            **entities,
        )


def _summary(row: dict[str, str]) -> str:
    """A short description with no IP, host or user in it, so Week 3 masking stays simple."""
    proto = norm.protocol(row["proto"])
    parts = [f"{norm.short(proto) if proto else 'unknown protocol'} flow"]
    for column, word in (("service", "service"), ("state", "state")):
        value = norm.clean(row[column])
        if value is not None:
            parts.append(f"{word} {norm.short(value)}")
    duration = norm.scalar(row["dur"])
    if isinstance(duration, int | float) and not isinstance(duration, bool):
        parts.append(f"{duration:.2f} s")
    for column, word in (("sbytes", "out"), ("dbytes", "in")):
        value = norm.scalar(row[column])
        if isinstance(value, int):
            parts.append(f"{value:,} B {word}")
    return ", ".join(parts)


def parse_unsw_nb15(path: Path, context: IntakeContext) -> Iterator[Event | Quarantined]:
    """Yield one Event or Quarantined per line read, in file order. A header line is skipped."""
    if not path.is_file():
        raise ParseError("The stored file is missing.")
    builder = _Builder(context)
    for line in read_lines(path):
        item = builder.record(line)
        if item is not None:
            yield item


def profile(path: Path) -> dict[str, Any]:
    """Aggregate-only profile of one UNSW-NB15 file, to fill label-mapping.json counts.

    It prints value counts of the label, attack-type, service, proto and state columns and
    the event-time range. It never outputs an IP, a port or any other entity value.
    """
    counters: dict[str, Counter[str]] = {
        name: Counter() for name in ("Label", "attack_cat", "service", "proto", "state")
    }
    lines = columns_bad = 0
    ip_state: Counter[str] = Counter()
    earliest: datetime | None = None
    latest: datetime | None = None
    for line in read_lines(path):
        if line.text is None:
            continue
        try:
            fields = _split(line.text)
        except csv.Error:
            columns_bad += 1
            continue
        if line.number == 1 and _is_header(fields):
            continue
        lines += 1
        if len(fields) != len(COLUMNS):
            columns_bad += 1
            continue
        row = dict(zip(COLUMNS, fields, strict=True))
        for name, counter in counters.items():
            counter[row[name]] += 1
        for column in ("srcip", "dstip"):
            if norm.clean(row[column]) is None:
                ip_state[f"{column}_empty"] += 1
            elif norm.ip_address(row[column]) is None:
                ip_state[f"{column}_not_an_ip"] += 1
            else:
                ip_state[f"{column}_valid"] += 1
        try:
            moment = norm.epoch_seconds(row["Stime"])
        except norm.BadValue:
            ip_state["Stime_bad"] += 1
            continue
        earliest = moment if earliest is None else min(earliest, moment)
        latest = moment if latest is None else max(latest, moment)
    return {
        "file": path.name,
        "data_lines": lines,
        "wrong_column_count_or_bad_csv": columns_bad,
        "event_time_min": earliest.isoformat() if earliest else None,
        "event_time_max": latest.isoformat() if latest else None,
        "address_columns": dict(sorted(ip_state.items())),
        "value_counts": {name: dict(counter.most_common(60)) for name, counter in counters.items()},
    }
