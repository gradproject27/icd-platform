"""Export a slice of a Precinct6 Parquet table to JSON lines for upload (risk-v1 step 3c).

    python -m app.ingest.precinct6_export signals/incident_signals.parquet --out leads.jsonl
    python -m app.ingest.precinct6_export signals/signals.parquet --out day.jsonl \\
        --start 2024-07-29T00:00:00Z --end 2024-07-30T00:00:00Z

One row becomes one JSON object per line, every column unchanged (the parser drops the CON-20
columns, not this tool). Datetime columns become epoch seconds, so `timestamp` stays epoch
seconds as in the card. Rows are read in batches, so memory stays small. --start and --end
filter on `timestamp` (start included, end excluded); --limit stops after that many rows.
The dataset profile's two slices: all of incident_signals (238,511 rows), and the live
signals of 29 Jul 2024 UTC (411,564 rows).

Needs pyarrow (requirements-dev.txt). The output holds real dataset rows: never commit it.
"""

import argparse
import json
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

BATCH_ROWS = 50_000


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.timestamp()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _epoch(value: Any) -> float | None:
    value = _plain(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _when(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC).timestamp()


def rows(
    path: Path, start: float | None = None, end: float | None = None, limit: int | None = None
) -> Iterator[dict[str, Any]]:
    """Rows of a Parquet file as plain dicts, filtered on timestamp, in file order."""
    import pyarrow.parquet as pq  # only needed here: the API image does not install pyarrow

    written = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=BATCH_ROWS):
        for row in batch.to_pylist():
            if start is not None or end is not None:
                moment = _epoch(row.get("timestamp"))
                if moment is None:
                    continue
                if (start is not None and moment < start) or (end is not None and moment >= end):
                    continue
            yield {str(key): _plain(value) for key, value in row.items()}
            written += 1
            if limit is not None and written >= limit:
                return


def export(path: Path, out: Path, **filters: Any) -> int:
    count = 0
    with out.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows(path, **filters):
            file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path, help="a Precinct6 .parquet table")
    parser.add_argument("--out", type=Path, required=True, help="JSON-lines file to write")
    parser.add_argument("--start", help="first timestamp to keep, ISO 8601 (UTC if no zone)")
    parser.add_argument("--end", help="timestamp to stop before, ISO 8601")
    parser.add_argument("--limit", type=int, help="stop after this many rows")
    args = parser.parse_args(argv)
    if not args.file.is_file():
        print(f"error: {args.file} is not a file", file=sys.stderr)
        return 2
    count = export(
        args.file,
        args.out,
        start=_when(args.start) if args.start else None,
        end=_when(args.end) if args.end else None,
        limit=args.limit,
    )
    print(f"wrote {count:,} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
