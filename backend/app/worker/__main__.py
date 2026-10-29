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
    from app.response.expiry import start_expiry_thread
    from app.worker.runner import run_forever

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    engine = get_engine()
    # C5: response windows expire on their own thread, so a long job never delays an expiry.
    expiry = start_expiry_thread(engine, stop)
    run_forever(engine, get_settings(), utcnow, stop)
    expiry.join(timeout=5)


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    main()
