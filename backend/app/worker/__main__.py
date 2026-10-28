"""Start the worker: python -m app.worker. Health check: python -m app.worker --check."""

import logging
import signal
import sys
import threading
import time

from app.db import get_engine
from app.jobs.queue import utcnow
from app.settings import get_settings
from app.worker.runner import HEARTBEAT_FILE

STALE_AFTER_SECONDS = 30


def check() -> int:
    try:
        age = time.time() - HEARTBEAT_FILE.stat().st_mtime
    except FileNotFoundError:
        return 1
    return 0 if age < STALE_AFTER_SECONDS else 1


def main() -> None:
    from app.worker.runner import run_forever

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run_forever(get_engine(), get_settings(), utcnow, stop)


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    main()
