"""Parser for dataset `fixture`: a JSON list of Events, like fixtures/correlation/events.json.

It lets the upload path run end to end before C2's dataset parsers land. The file is read
whole, so it is meant for small synthetic files only.
"""

import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from app.contracts import Event
from app.ingest.interface import IntakeContext, ParseError, Quarantined


def parse_fixture(path: Path, context: IntakeContext) -> Iterator[Event | Quarantined]:
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ParseError("The file is not UTF-8 text.") from exc
    except json.JSONDecodeError as exc:
        raise ParseError(f"The file is not valid JSON (line {exc.lineno}).") from exc
    if not isinstance(records, list):
        raise ParseError("A fixture file must be a JSON list of Events.")

    for index, record in enumerate(records, start=1):
        ref = f"{context.source_file}:{index}"
        excerpt = json.dumps(record, ensure_ascii=False)
        try:
            yield Event.model_validate(record)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "record"
            yield Quarantined(
                record_ref=ref,
                reason_code="invalid_event",
                reason=f"{where}: {first['msg']}",
                raw_excerpt=excerpt,
            )
