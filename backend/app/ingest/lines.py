"""Read a text file line by line without trusting it (plan section 5 watch-outs).

A line that is too long or not UTF-8 is reported, never raised, so one bad line cannot stop
the file. Lines are numbered from 1 as a text editor shows them, which is what
Provenance.record_ref points at.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

MAX_LINE_BYTES = 64 * 1024
EXCERPT_BYTES = 500


@dataclass(frozen=True)
class Line:
    """One physical line. text is None when the line has a problem (code and reason set)."""

    number: int
    text: str | None
    code: str | None = None
    reason: str | None = None
    excerpt: str | None = None


def excerpt(data: bytes | str) -> str:
    """The start of a line, safe to store: decoded leniently, no NUL (Postgres rejects it)."""
    if isinstance(data, bytes):
        data = data[:EXCERPT_BYTES].decode("utf-8", errors="replace")
    return data[:EXCERPT_BYTES].replace("\x00", "�")


def read_lines(path: Path, max_bytes: int = MAX_LINE_BYTES) -> Iterator[Line]:
    """Yield every line of the file in order, without its line ending."""
    with path.open("rb") as file:
        number = 0
        while chunk := file.readline(max_bytes + 1):
            number += 1
            if len(chunk) > max_bytes and not chunk.endswith(b"\n"):
                while (rest := file.readline(max_bytes + 1)) and not rest.endswith(b"\n"):
                    pass
                yield Line(
                    number,
                    None,
                    "line_too_long",
                    f"the line is longer than {max_bytes} bytes",
                    excerpt(chunk),
                )
                continue
            raw = chunk.rstrip(b"\r\n")
            if number == 1 and raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                yield Line(
                    number,
                    None,
                    "bad_encoding",
                    f"byte {exc.start + 1} of the line is not UTF-8",
                    excerpt(raw),
                )
                continue
            if "\x00" in text:
                yield Line(
                    number, None, "bad_encoding", "the line contains a NUL byte", excerpt(text)
                )
                continue
            yield Line(number, text)


def line_number(record_ref: str) -> int:
    """The line number in a record_ref of the form <file name>:<line>."""
    _, _, number = record_ref.rpartition(":")
    if not number.isdigit() or int(number) < 1:
        raise ValueError(f"{record_ref!r} does not end with :<line number>")
    return int(number)


def read_original(path: Path, record_ref: str) -> str:
    """The original line an Event or quarantined record points at (FR-05).

    Streams the file, so it is fine for a demo or a single lookup, not for bulk use.
    """
    wanted = line_number(record_ref)
    with path.open("rb") as file:
        for number, chunk in enumerate(file, start=1):
            if number == wanted:
                return chunk.rstrip(b"\r\n").decode("utf-8", errors="replace")
    raise LookupError(f"{path.name} has fewer than {wanted} lines")
