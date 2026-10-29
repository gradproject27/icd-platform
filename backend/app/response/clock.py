"""The response engine's clock (decision D4).

The running system reads the time from PostgreSQL, so the API and the worker share one clock and
`deadline_at` means the same instant to both (spec section 7). Tests pass a FakeClock and move it
by hand, so no test waits 60 real seconds.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import Engine, text


class Clock(Protocol):
    def now(self) -> datetime: ...


class DatabaseClock:
    """Database time: clock_timestamp(), the real time even inside a long transaction."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def now(self) -> datetime:
        with self.engine.connect() as connection:
            value = connection.execute(text("SELECT clock_timestamp()")).scalar_one()
        return value.astimezone(UTC)


class FakeClock:
    """A clock that only moves when a test tells it to."""

    def __init__(self, start: datetime):
        if start.tzinfo is None:
            raise ValueError("start must be timezone-aware")
        self.current = start.astimezone(UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> datetime:
        self.current += timedelta(seconds=seconds)
        return self.current
