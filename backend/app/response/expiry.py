"""The expiry worker (FR-27, AS-10; decision D5): a loop thread inside the worker process.

It runs next to C1's job loop, not inside it, so a long ingest job never delays an expiry. Each
pass closes every due window exactly once; a second pass, a restart or a second worker only finds
windows that are already closed (expiry_duplicate_ignored is written for a lost race).
"""

import logging
import threading

from sqlalchemy import Engine

from app.response.clock import Clock, DatabaseClock
from app.response.engine import ResponseEngine

log = logging.getLogger("icd.response.expiry")

POLL_SECONDS = 0.5


def run_expiry_loop(
    engine: Engine, stop: threading.Event, clock: Clock | None = None, poll: float = POLL_SECONDS
) -> None:
    response = ResponseEngine(engine, clock or DatabaseClock(engine))
    log.info("response expiry loop started")
    while not stop.is_set():
        try:
            for outcome in response.expire_due():
                log.info("window %s: %s", outcome.window_id, outcome.result.value)
            for action_id in response.run_pending_actions():
                log.warning("approved action %s was not simulated yet; simulated now", action_id)
        except Exception:  # database down: keep the loop alive and try again
            log.exception("response expiry loop error")
        stop.wait(poll)


def start_expiry_thread(engine: Engine, stop: threading.Event) -> threading.Thread:
    thread = threading.Thread(
        target=run_expiry_loop, args=(engine, stop), name="response-expiry", daemon=True
    )
    thread.start()
    return thread
