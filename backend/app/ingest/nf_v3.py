"""Parser for the NetFlow v3 datasets of the University of Queensland (risk-v1 step 3a).

Two dataset IDs share this parser because their CSV header is the same (checked by the user on
25 Nov 2026 in both files): `nf-unsw-nb15-v3` (NF-UNSW-NB15-v3) and `nf-cse-cic-ids2018-v3`
(NF-CSE-CIC-IDS2018-v3). Dataset page: https://staff.itee.uq.edu.au/marius/NIDS_datasets/.

One line is one flow. Line 1 must be the 55-column header below; any other first line stops
the file with ParseError, because every later column is read by its position. After it, every
line read becomes an Event or a Quarantined record with its reason, in file order; one bad line
never stops the file (docs/api-upload-jobs.md section 5). Field rules: docs/ingestion.md
section 9.
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

DATASET_IDS = frozenset({"nf-unsw-nb15-v3", "nf-cse-cic-ids2018-v3"})

# The 55 columns in file order, exactly as in line 1 of both files (25 Nov 2026).
COLUMNS = (
    "FLOW_START_MILLISECONDS", "FLOW_END_MILLISECONDS", "IPV4_SRC_ADDR", "L4_SRC_PORT",
    "IPV4_DST_ADDR", "L4_DST_PORT", "PROTOCOL", "L7_PROTO", "IN_BYTES", "IN_PKTS",
    "OUT_BYTES", "OUT_PKTS", "TCP_FLAGS", "CLIENT_TCP_FLAGS", "SERVER_TCP_FLAGS",
    "FLOW_DURATION_MILLISECONDS", "DURATION_IN", "DURATION_OUT", "MIN_TTL", "MAX_TTL",
    "LONGEST_FLOW_PKT", "SHORTEST_FLOW_PKT", "MIN_IP_PKT_LEN", "MAX_IP_PKT_LEN",
    "SRC_TO_DST_SECOND_BYTES", "DST_TO_SRC_SECOND_BYTES", "RETRANSMITTED_IN_BYTES",
    "RETRANSMITTED_IN_PKTS", "RETRANSMITTED_OUT_BYTES", "RETRANSMITTED_OUT_PKTS",
    "SRC_TO_DST_AVG_THROUGHPUT", "DST_TO_SRC_AVG_THROUGHPUT", "NUM_PKTS_UP_TO_128_BYTES",
    "NUM_PKTS_128_TO_256_BYTES", "NUM_PKTS_256_TO_512_BYTES", "NUM_PKTS_512_TO_1024_BYTES",
    "NUM_PKTS_1024_TO_1514_BYTES", "TCP_WIN_MAX_IN", "TCP_WIN_MAX_OUT", "ICMP_TYPE",
    "ICMP_IPV4_TYPE", "DNS_QUERY_ID", "DNS_QUERY_TYPE", "DNS_TTL_ANSWER",
    "FTP_COMMAND_RET_CODE", "SRC_TO_DST_IAT_MIN", "SRC_TO_DST_IAT_MAX", "SRC_TO_DST_IAT_AVG",
    "SRC_TO_DST_IAT_STDDEV", "DST_TO_SRC_IAT_MIN", "DST_TO_SRC_IAT_MAX", "DST_TO_SRC_IAT_AVG",
    "DST_TO_SRC_IAT_STDDEV", "Label", "Attack",
)  # fmt: skip

# Mapped to Event fields. Label and Attack only ever reach EventLabel, never extra_fields,
# so correlation cannot read the label from a side field.
MAPPED = frozenset(
    {
        "FLOW_START_MILLISECONDS", "IPV4_SRC_ADDR", "L4_SRC_PORT", "IPV4_DST_ADDR",
        "L4_DST_PORT", "PROTOCOL", "Label", "Attack",
    }
)  # fmt: skip
# Kept as text in extra_fields: L7_PROTO is "<master id>.<app id>" (for example "7.178"),
# which would lose digits as a float.
AS_TEXT = frozenset({"L7_PROTO"})
EXTRA = tuple(name for name in COLUMNS if name not in MAPPED)

# Attack value of a Label 0 (normal) flow. Spelling as on the dataset page; any other value
# under Label 0 is quarantined (label_attack_mismatch), never dropped or guessed.
BENIGN = "Benign"


def _split(text: str) -> list[str]:
    return next(csv.reader([text]), [])


def l7_master(value: str | None) -> str | None:
    """The nDPI master protocol ID of an L7_PROTO value: "7.178" -> "7", "91" -> "91"."""
    text = norm.clean(value)
    if text is None:
        return None
    master = text.split(".", 1)[0].strip()
    return master if master.isdigit() else None


protocol_name = norm.iana_protocol


def _check_header(first: Line | None) -> None:
    if first is None:
        return
    fields = _split(first.text) if first.text is not None else []
    if tuple(field.strip() for field in fields) != COLUMNS:
        raise ParseError(
            "Line 1 is not the NetFlow v3 header (55 columns, FLOW_START_MILLISECONDS to "
            "Attack). Upload the file, or a slice of it, with its header line."
        )


class _Builder:
    def __init__(self, context: IntakeContext) -> None:
        self.context = context
        self.labels = LabelMap(context.dataset_id)
        self.types = EventTypes(context.dataset_id)
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

    def record(self, line: Line) -> Event | Quarantined:
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
        if len(fields) != len(COLUMNS):
            return self.quarantined(
                line.number,
                "wrong_column_count",
                f"{len(fields)} columns, expected {len(COLUMNS)}",
                text,
            )
        row = dict(zip(COLUMNS, fields, strict=True))
        if norm.clean(row["FLOW_START_MILLISECONDS"]) is None:
            return self.quarantined(
                line.number,
                "missing_timestamp",
                "FLOW_START_MILLISECONDS (event time) is empty",
                text,
            )
        try:
            timestamp = norm.epoch_millis(row["FLOW_START_MILLISECONDS"])
        except norm.BadValue as exc:
            return self.quarantined(
                line.number, "bad_timestamp", f"FLOW_START_MILLISECONDS: {exc}", text
            )
        try:
            return self.event(line.number, row, timestamp)
        except LabelProblem as exc:
            return self.quarantined(line.number, exc.code, exc.reason, text)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "record"
            return self.quarantined(line.number, "invalid_event", f"{where}: {first['msg']}", text)

    def attack_type(self, label_raw: str, attack_raw: str) -> str | None:
        """Attack type for EventLabel: only on Label 1, only a spelling the mapping lists."""
        attack = attack_raw.strip()
        shown = attack if len(attack) <= 40 else attack[:39] + "…"
        if label_raw == "1":
            if attack not in self.labels.attack_types:
                raise LabelProblem(
                    "unknown_attack_type",
                    f"Attack {shown!r} is not in label-mapping.json for {self.labels.dataset_id}",
                )
            return attack
        if label_raw == "0" and attack not in ("", BENIGN):
            raise LabelProblem(
                "label_attack_mismatch",
                f"Label 0 (normal) but Attack is {shown!r}, not {BENIGN!r}",
            )
        return None

    def event(self, number: int, row: dict[str, str], timestamp: datetime) -> Event:
        extra: dict[str, Any] = {
            name: (norm.clean(row[name]) if name in AS_TEXT else norm.scalar(row[name]))
            for name in EXTRA
        }
        entities: dict[str, Any] = {}
        for column, field, convert in (
            ("IPV4_SRC_ADDR", "src_ip", norm.ip_address),
            ("IPV4_DST_ADDR", "dst_ip", norm.ip_address),
            ("L4_SRC_PORT", "src_port", norm.port),
            ("L4_DST_PORT", "dst_port", norm.port),
        ):
            value = convert(row[column])
            entities[field] = value
            original = norm.clean(row[column])
            if value is None and original is not None:
                extra[f"{column}_raw"] = norm.short(original, 100)

        self.labels.label(row["Label"])  # unknown or pending Label first, as in UNSW-NB15
        attack_type = self.attack_type(row["Label"], row["Attack"])
        label = self.labels.label(row["Label"], attack_type)
        return Event(
            event_id=f"{self.context.dataset_id}:{self.stem}:{number}",
            timestamp=timestamp,
            ingested_at=self.context.ingested_at,
            event_type=self.types.event_type(l7_master(row[self.types.field])),
            label=label,
            host=None,
            protocol=protocol_name(row["PROTOCOL"]),
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
    """A short description with no IP, host or user in it, so masking stays simple."""
    proto = protocol_name(row["PROTOCOL"])
    parts = [f"{norm.short(proto) if proto else 'unknown protocol'} flow"]
    l7 = norm.clean(row["L7_PROTO"])
    if l7 is not None:
        parts.append(f"L7 {norm.short(l7, 12)}")
    duration = norm.scalar(row["FLOW_DURATION_MILLISECONDS"])
    if isinstance(duration, int | float) and not isinstance(duration, bool):
        parts.append(f"{duration:,} ms")
    for column, words in (("IN_BYTES", "src to dst"), ("OUT_BYTES", "dst to src")):
        value = norm.scalar(row[column])
        if isinstance(value, int):
            parts.append(f"{value:,} B {words}")
    return ", ".join(parts)


def parse_nf_v3(path: Path, context: IntakeContext) -> Iterator[Event | Quarantined]:
    """Yield one Event or Quarantined per line after the header, in file order."""
    if context.dataset_id not in DATASET_IDS:
        raise ParseError(f"The NetFlow v3 parser does not read dataset {context.dataset_id}.")
    if not path.is_file():
        raise ParseError("The stored file is missing.")
    builder = _Builder(context)
    lines = read_lines(path)
    _check_header(next(lines, None))
    for line in lines:
        yield builder.record(line)


def profile(path: Path) -> dict[str, Any]:
    """Aggregate-only profile of one NetFlow v3 file, to fill label-mapping.json counts.

    It prints value counts of Label, Attack, (Label, Attack) pairs, PROTOCOL and the L7_PROTO
    master ID, and the event-time range. It never outputs an IP, a port or any other entity.
    """
    counters: dict[str, Counter[str]] = {
        name: Counter() for name in ("Label", "Attack", "Label|Attack", "PROTOCOL", "L7_master")
    }
    lines = columns_bad = time_bad = 0
    earliest: datetime | None = None
    latest: datetime | None = None
    reader = read_lines(path)
    _check_header(next(reader, None))
    for line in reader:
        if line.text is None:
            columns_bad += 1
            continue
        try:
            fields = _split(line.text)
        except csv.Error:
            columns_bad += 1
            continue
        lines += 1
        if len(fields) != len(COLUMNS):
            columns_bad += 1
            continue
        row = dict(zip(COLUMNS, fields, strict=True))
        counters["Label"][row["Label"]] += 1
        counters["Attack"][row["Attack"]] += 1
        counters["Label|Attack"][f"{row['Label']}|{row['Attack']}"] += 1
        counters["PROTOCOL"][row["PROTOCOL"]] += 1
        counters["L7_master"][l7_master(row["L7_PROTO"]) or "(none)"] += 1
        try:
            moment = norm.epoch_millis(row["FLOW_START_MILLISECONDS"])
        except norm.BadValue:
            time_bad += 1
            continue
        earliest = moment if earliest is None else min(earliest, moment)
        latest = moment if latest is None else max(latest, moment)
    return {
        "file": path.name,
        "data_lines": lines,
        "wrong_column_count_or_bad_csv": columns_bad,
        "bad_event_time": time_bad,
        "event_time_min": earliest.isoformat() if earliest else None,
        "event_time_max": latest.isoformat() if latest else None,
        "value_counts": {name: dict(counter.most_common(60)) for name, counter in counters.items()},
    }
