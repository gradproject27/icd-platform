"""Build the masked evidence packages of an events file (demo and checks, no database).

    python -m app.evidence.cli ../fixtures/correlation/events.json
    python -m app.evidence.cli ../fixtures/correlation/events.json --incident inc-e8d1f72159481bee

It correlates and scores the events with C3's code, builds one package per incident and
prints a one-line summary each, or the whole masked package of one incident. The masking map
(the real values) is never printed.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.contracts import Event
from app.correlation import correlate, load_config, score_incidents
from app.evidence.builder import build_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.evidence.cli", description=__doc__)
    parser.add_argument("events", type=Path, help="JSON list of Events")
    parser.add_argument("--incident", help="print the whole package of this incident")
    args = parser.parse_args(argv)

    events = [Event.model_validate(e) for e in json.loads(args.events.read_text("utf-8"))]
    now = datetime.now(UTC)
    config = load_config()
    incidents = score_incidents(correlate(events, config, now).incidents, events, now,
                                correlation=config)  # fmt: skip
    for incident in incidents:
        package, masked = build_package(incident, events, now)
        if args.incident == incident.incident_id:
            print(json.dumps(package.model_dump(mode="json"), indent=2))
            return 0
        if args.incident is None:
            print(
                f"{incident.incident_id}  {len(package.events):>2}/{package.total_event_count:<3}"
                f" events  truncated={str(package.truncated).lower():<5}  "
                f"tokens={len(masked.masking_map.tokens)}  {package.package_id}"
            )
    if args.incident is not None:
        print(f"error: no incident {args.incident}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
