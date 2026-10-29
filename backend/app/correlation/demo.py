"""Friday demo: correlate an events file, score the incidents and print them.

Usage (from backend/): python -m app.correlation.demo EVENTS_JSON [ASSETS_TOML]
ASSETS_TOML adds asset levels; for the fixture use ../fixtures/correlation/assets.toml.
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.contracts import Event, EventRole
from app.correlation import correlate, load_config, load_risk_config, score_incidents


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    raw = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    events = [Event.model_validate(e) for e in raw]
    by_id = {e.event_id: e for e in events}
    config = load_config()
    risk_config = load_risk_config(assets_path=Path(argv[1]) if len(argv) == 2 else None)
    now = datetime.now(UTC)
    started = time.perf_counter()
    result = correlate(events, config, now)
    incidents = score_incidents(result.incidents, events, now, risk_config, config)
    elapsed_ms = (time.perf_counter() - started) * 1000

    print(
        f"{len(events)} events -> {len(incidents)} incidents "
        f"({config.config_version}, {risk_config.config_version})"
    )
    print(
        f"{'incident':<22} {'flagged':>7} {'context':>7}  {'span':<13} {'type':<15} "
        f"{'risk':>4} {'level':<6} hosts"
    )
    for inc in sorted(incidents, key=lambda i: (-i.risk.score, i.incident_id)):
        flagged = [link for link in inc.events if link.role == EventRole.FLAGGED]
        hosts = sorted({by_id[link.event_id].host for link in flagged} - {None})
        span = f"{inc.first_event_at:%H:%M}-{inc.last_event_at:%H:%M}"
        print(
            f"{inc.incident_id:<22} {len(flagged):>7} {len(inc.events) - len(flagged):>7}  "
            f"{span:<13} {inc.incident_type or '(none)':<15} {inc.risk.score:>4} "
            f"{inc.risk.level.value:<6} {', '.join(hosts) or '(none)'}"
        )
        top = inc.risk.top_contributors[0]
        flags = ", ".join(f.value for f in inc.risk.flags) or "none"
        print(
            f"{'':<22} L={inc.risk.likelihood:.2f} I={inc.risk.impact:.2f}; "
            f"top: {top.technique} from {top.entity} ({top.strength:.2f}); flags: {flags}"
        )
    flagged_total = sum(e.label.status == "flagged" for e in events)
    if incidents:
        print(f"alert compression: {flagged_total / len(incidents):.2f} flagged per incident")
        levels = [i.risk.level.value for i in incidents]
        print(
            "levels: " + ", ".join(f"{lv} {levels.count(lv)}" for lv in ("high", "medium", "low"))
        )
    print(f"outside any incident: {len(result.unassigned_event_ids)} events")
    print(f"runtime: {elapsed_ms:.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
