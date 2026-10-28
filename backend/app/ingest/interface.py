"""How the worker calls a parser (decision D10; docs/api-upload-jobs.md section 5).

A parser reads one stored file and yields one item per record read, in file order: an Event,
or a Quarantined record with its reason. It never raises for one bad record; it raises
ParseError only when the whole file cannot be read. It never writes to the database.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.contracts import Event

EXCERPT_CHARS = 500


@dataclass(frozen=True)
class IntakeContext:
    """What a parser needs besides the file, so every Event gets the same provenance."""

    upload_id: str
    dataset_id: str
    source_file: str
    ingested_at: datetime


@dataclass(frozen=True)
class Quarantined:
    """A record that could not become an Event (FR-03). The worker numbers it (seq)."""

    record_ref: str
    reason_code: str
    reason: str
    raw_excerpt: str | None = None

    def __post_init__(self) -> None:
        # PostgreSQL text cannot hold NUL, so it is dropped from the stored strings.
        for name in ("record_ref", "reason"):
            object.__setattr__(self, name, getattr(self, name).replace("\x00", ""))
        if self.raw_excerpt is not None:
            excerpt = self.raw_excerpt.replace("\x00", "")[:EXCERPT_CHARS]
            object.__setattr__(self, "raw_excerpt", excerpt)


class ParseError(Exception):
    """The whole file cannot be parsed. The message is shown to the user."""


Parser = Callable[[Path, IntakeContext], Iterator[Event | Quarantined]]
