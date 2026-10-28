"""Normalizer: turn source field values into Event field values (plan section 5, step 3).

Pure functions only: the same input always gives the same output, with no clock, no lookup
and no guess. A value that cannot be normalized becomes null and the caller keeps the
original in extra_fields; only a bad timestamp makes a record unusable (FR-03).
"""

import ipaddress
import re
from datetime import UTC, datetime

from app.contracts.common import JsonScalar

# Values that mean "no value" in the sources profiled in Week 1 (dataset-profile.md section 6).
SENTINELS = frozenset({"", "-"})

# Event times outside this range are treated as bad data, not as real activity.
EARLIEST = datetime(1990, 1, 1, tzinfo=UTC)
LATEST = datetime(2100, 1, 1, tzinfo=UTC)

_INT = re.compile(r"^[+-]?\d+$")
_FLOAT = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_NOT_ID = re.compile(r"[^A-Za-z0-9._-]+")


class BadValue(ValueError):
    """A value that cannot be normalized. The message is shown in the quarantine reason."""


def clean(value: str | None) -> str | None:
    """Trim spaces; a sentinel such as "" or "-" becomes None."""
    if value is None:
        return None
    value = value.strip()
    return None if value in SENTINELS else value


def epoch_seconds(value: str | None) -> datetime:
    """Epoch seconds (UTC by definition) to an aware UTC datetime.

    Raises BadValue when the value is missing, not a number or outside 1990 to 2100.
    """
    text = clean(value)
    if text is None:
        raise BadValue("no event time")
    if not _FLOAT.match(text):
        raise BadValue(f"event time {text[:40]!r} is not epoch seconds")
    try:
        moment = datetime.fromtimestamp(float(text), tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise BadValue(f"event time {text[:40]!r} is out of range") from exc
    if not EARLIEST <= moment < LATEST:
        raise BadValue(f"event time {moment.isoformat()} is outside 1990 to 2100")
    return moment


def ip_address(value: str | None) -> str | None:
    """A valid IPv4 or IPv6 address in canonical text form, else None. Never resolved."""
    text = clean(value)
    if text is None:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def port(value: str | None) -> int | None:
    """A port from decimal or hex ("0x000b") text, else None. Range 0 to 65535."""
    text = clean(value)
    if text is None:
        return None
    try:
        number = int(text, 16) if text.lower().startswith("0x") else int(text, 10)
    except ValueError:
        return None
    return number if 0 <= number <= 65535 else None


def protocol(value: str | None) -> str | None:
    """Lower-case protocol name, for example "tcp"."""
    text = clean(value)
    return text.lower() if text is not None else None


def scalar(value: str | None) -> JsonScalar:
    """A source column for extra_fields: int, float or the trimmed text; sentinels to None."""
    text = clean(value)
    if text is None:
        return None
    if _INT.match(text):
        return int(text)
    if _FLOAT.match(text):
        number = float(text)
        if number == number and number not in (float("inf"), float("-inf")):
            return number
    return text


def id_part(text: str, limit: int = 60) -> str:
    """Cut text to the Event ID character set, for use inside an event_id."""
    part = _NOT_ID.sub("_", text).strip("._-")[:limit]
    return part or "file"


def short(text: str, limit: int = 40) -> str:
    """Shorten a source value before it goes into a summary."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
