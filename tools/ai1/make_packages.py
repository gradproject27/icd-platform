"""Build the five AI1 test packages from C3's correlation fixture (AI1, Week 2).

Run from the repo root:  python tools/ai1/make_packages.py
It correlates and scores fixtures/correlation/events.json with C3's code, builds each chosen
incident's masked EvidencePackage with C2's builder, and writes fixtures/ai1/packages/<name>.json.
The clock is fixed, so the files are identical on every machine; a test checks they are current.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.contracts import Event  # noqa: E402
from app.correlation import correlate, load_config, score_incidents  # noqa: E402
from app.evidence.builder import build_package  # noqa: E402

EVENTS = ROOT / "fixtures" / "correlation" / "events.json"
OUT_DIR = ROOT / "fixtures" / "ai1" / "packages"
NOW = datetime(2026, 1, 15, 23, 0, tzinfo=UTC)

# file name -> the fixture event that starts the incident (fixtures/correlation/README.md)
CHOSEN = {
    "a-multistep-high": "fx-002",
    "c1-fuzzers-low": "fx-021",
    "c2-dos-medium": "fx-025",
    "e-no-attack-type": "fx-032",
    "f-no-entities": "fx-005",
}


def build() -> dict[str, str]:
    """File name -> exact file text."""
    events = [Event.model_validate(e) for e in json.loads(EVENTS.read_text("utf-8"))]
    config = load_config()
    incidents = score_incidents(
        correlate(events, config, NOW).incidents, events, NOW, correlation=config
    )
    by_start = {i.events[0].event_id: i for i in incidents}
    files = {}
    for name, start in CHOSEN.items():
        package, _ = build_package(by_start[start], events, NOW)
        files[f"{name}.json"] = json.dumps(package.model_dump(mode="json"), indent=2) + "\n"
    return files


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in build().items():
        with (OUT_DIR / name).open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {OUT_DIR / name}")


if __name__ == "__main__":
    main()
