"""C1 demo reset (roadmap task 26, decision F9): one command back to a clean, loaded demo.

Standard library only; run from the repo root with the stack up (docker compose up -d --wait):

    python tools/c1/demo_reset.py                         empty, then load the default demo file
    python tools/c1/demo_reset.py --file <slice.csv> --dataset-id unsw-nb15   C2's demo slice
    python tools/c1/demo_reset.py --no-upload             only empty the platform

Steps: stop the worker (no job half-runs during the reset), empty every app table and the
stored uploads in a one-off worker container (app/demo/reset.py; the schema stays), start the
worker, upload the demo file, and wait until it is ingested, correlated and every incident is
analysed. Then it prints each incident's risk level, analysis and lifecycle status, and the
response windows that opened, which is where demo paths A and B start.

The default file is the C3 correlation fixture: with the stub model it gives one High incident
that freezes (a response window opens) and others that do not.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from week2_demo import call, upload, watch  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DEFAULT_FILE = REPO / "fixtures" / "correlation" / "events.json"


def compose(*args: str) -> None:
    print(f"    docker compose {' '.join(args)}")
    subprocess.run(["docker", "compose", *args], cwd=REPO, check=True)


def wait_for_analysis(base: str, upload_id: str, timeout: float) -> list[dict]:
    """Poll the upload's incidents until every one has an analysis result (or time is up)."""
    deadline = time.monotonic() + timeout
    while True:
        _, page = call("GET", f"{base}/incidents?upload_id={upload_id}")
        items = page["items"]
        pending = [
            i for i in items if i["incident"]["analysis_status"] in ("not_started", "in_progress")
        ]
        print(
            f"    {time.strftime('%H:%M:%S')}  {len(items) - len(pending)} of {len(items)} analysed"
        )
        if not pending or time.monotonic() > deadline:
            return items
        time.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8080/api")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--dataset-id", default="fixture")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--timeout", type=float, default=600, help="seconds to wait per step")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print("== 1. Empty the platform")
    compose("stop", "worker")
    try:
        compose(
            "run", "--rm", "--no-deps", "-e", "ICD_ALLOW_RESET=1", "worker",
            "python", "-m", "app.demo.reset",
        )  # fmt: skip
    finally:
        compose("start", "worker")
    if args.no_upload:
        return 0

    print(f"\n== 2. Upload {args.file.name} ({args.dataset_id})")
    status, accepted = upload(base, args.file.name, args.file.read_bytes(), args.dataset_id)
    if status != 202:
        print(f"    upload refused: HTTP {status} {accepted}")
        return 1
    job = watch(base, accepted["job_id"], args.timeout)
    if job["state"] != "done":
        print(f"    ingest job {job['state']}: {job.get('error')}")
        return 1
    print(f"    counts: {job['counts']}")

    print("\n== 3. Wait for the AI analysis of every incident")
    items = wait_for_analysis(base, accepted["upload_id"], args.timeout)

    print("\n== 4. Ready for the demo")
    frozen = 0
    for item in items:
        incident = item["incident"]
        _, window = call("GET", f"{base}/response-windows/{incident['incident_id']}")
        is_open = isinstance(window, dict) and window.get("status") == "open"
        frozen += is_open
        risk = (incident.get("risk") or {}).get("level")
        print(
            f"    {incident['incident_id']}  risk={risk}  analysis={incident['analysis_status']}"
            f"  confidence={incident['confidence']}" + ("  RESPONSE WINDOW OPEN" if is_open else "")
        )
    print(f"\n    {len(items)} incidents, {frozen} with an open response window")
    analysed = all(i["incident"]["analysis_status"] in ("succeeded", "failed") for i in items)
    return 0 if items and analysed else 1


if __name__ == "__main__":
    raise SystemExit(main())
