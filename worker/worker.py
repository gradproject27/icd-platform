"""Background worker placeholder.

It only writes a heartbeat so Compose can health-check it. Real jobs (ingestion,
correlation, LLM analysis) are added by their owning workstreams.
"""

import sys
import time
from pathlib import Path

HEARTBEAT = Path("/tmp/worker-heartbeat")
INTERVAL_SECONDS = 5
STALE_AFTER_SECONDS = 30


def check() -> int:
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
    except FileNotFoundError:
        return 1
    return 0 if age < STALE_AFTER_SECONDS else 1


def run() -> None:
    print("worker started (placeholder, no jobs yet)", flush=True)
    while True:
        HEARTBEAT.touch()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    run()
