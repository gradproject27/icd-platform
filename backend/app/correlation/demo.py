"""Friday demo: correlate an events file and print the incidents.

Usage (from backend/): python -m app.correlation.demo ../fixtures/correlation/events.json
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.contracts import Event, EventRole
from app.correlation import correlate, load_config


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    raw = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    events = [Event.model_validate(e) for e in raw]
    by_id = {e.event_id: e for e in events}
    config = load_config()
    started = time.perf_counter()
    result = correlate(events, config, datetime.now(UTC))
    elapsed_ms = (time.perf_counter() - started) * 1000

    print(f"{len(events)} events -> {len(result.incidents)} incidents ({config.config_version})")
    print(f"{'incident':<22} {'flagged':>7} {'context':>7}  {'span':<13} {'type':<15} hosts")
    for inc in result.incidents:
        flagged = [link for link in inc.events if link.role == EventRole.FLAGGED]
        hosts = sorted({by_id[link.event_id].host for link in flagged} - {None})
        span = f"{inc.first_event_at:%H:%M}-{inc.last_event_at:%H:%M}"
        print(
            f"{inc.incident_id:<22} {len(flagged):>7} {len(inc.events) - len(flagged):>7}  "
            f"{span:<13} {inc.incident_type or '(none)':<15} {', '.join(hosts) or '(none)'}"
        )
    flagged_total = sum(e.label.status == "flagged" for e in events)
    if result.incidents:
        print(
            f"alert compression: {flagged_total / len(result.incidents):.2f} flagged per incident"
        )
    print(f"outside any incident: {len(result.unassigned_event_ids)} events")
    print(f"runtime: {elapsed_ms:.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
