"""C1 Week 2 demo: upload a file, watch its job, query its events and quarantined records.

Standard library only, so it runs with any Python 3.12 on Windows or Linux:

    docker compose up --build --detach --wait
    python tools/c1/week2_demo.py                       (default base URL http://localhost:8080/api)
    python tools/c1/week2_demo.py --base-url http://localhost:8000

It shows the Week 2 C1 "done means": upload a file, see a job ID at once, watch the status
change, and query what was stored, with every rejected record accounted for. Only files from
the repo are used (the synthetic fixture and C2's 30-line UNSW-NB15 sample). The HPC handoff
is not part of this demo.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "fixtures" / "correlation" / "events.json"
UNSW_SAMPLE = REPO / "fixtures" / "ingest" / "unsw-nb15-sample.csv"


def call(method: str, url: str, body: bytes | None = None, content_type: str | None = None):
    request = urllib.request.Request(url, data=body, method=method)
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def upload(base: str, name: str, content: bytes, dataset_id: str):
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="dataset_id"\r\n\r\n'
        f"{dataset_id}\r\n".encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode()
        + content
        + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    status, body = call(
        "POST", f"{base}/uploads", b"".join(parts), f"multipart/form-data; boundary={boundary}"
    )
    error = (body or {}).get("error") if isinstance(body, dict) else None
    if status == 409 and error and error["code"] == "duplicate_upload":
        # Run again on the same stack: the duplicate-upload guard (C2) refuses the same file
        # and names the earlier upload, so the demo shows that one instead.
        earlier = re.search(r"upl-[0-9a-f]+", error["message"]).group(0)
        print(f"    {name} was already uploaded as {earlier} (409 duplicate_upload); using it")
        _, shown = call("GET", f"{base}/uploads/{earlier}")
        return 202, {"upload_id": shown["upload_id"], "job_id": shown["job_id"]}
    return status, body


def watch(base: str, job_id: str, timeout: float) -> dict:
    """Poll the job about once a second and print every change of state or stage."""
    last = None
    deadline = time.monotonic() + timeout
    while True:
        _, job = call("GET", f"{base}/jobs/{job_id}")
        now = (job["state"], job["stage"])
        if now != last:
            stage = f" ({job['stage']})" if job["stage"] else ""
            print(f"    {time.strftime('%H:%M:%S')}  {job['state']}{stage}")
            last = now
        if job["state"] in ("done", "failed") or time.monotonic() > deadline:
            return job
        time.sleep(1)


def heading(text: str) -> None:
    print(f"\n== {text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8080/api")
    parser.add_argument("--timeout", type=float, default=120, help="seconds to wait per job")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    ok = True

    heading("Health")
    status, body = call("GET", f"{base}/health")
    print(f"    HTTP {status} {body}")

    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    heading(f"1. Upload the C3 correlation fixture ({len(records)} synthetic events)")
    status, accepted = upload(base, FIXTURE.name, FIXTURE.read_bytes(), "fixture")
    print(f"    HTTP {status}: upload {accepted['upload_id']}, job {accepted['job_id']}")
    ok &= status == 202
    job = watch(base, accepted["job_id"], args.timeout)
    print(f"    counts: {json.dumps(job['counts'])}")
    ok &= job["state"] == "done" and (job["counts"] or {}).get("events_stored") == len(records)
    _, page = call(
        "GET", f"{base}/uploads/{accepted['upload_id']}/events?label_status=flagged&limit=3"
    )
    print("    first flagged events (queryable, with their label and original record):")
    for event in page["items"]:
        ref = event["provenance"]
        print(
            f"      {event['event_id']}  {event['timestamp']}  {event['event_type']:<16} "
            f"label={event['label']['status']}  from {ref['source_file']}:{ref['record_ref']}"
        )

    heading("2. Upload C2's UNSW-NB15 sample through the real parser")
    status, accepted = upload(base, UNSW_SAMPLE.name, UNSW_SAMPLE.read_bytes(), "unsw-nb15")
    job = watch(base, accepted["job_id"], args.timeout)
    counts = job["counts"] or {}
    print(f"    counts: {json.dumps(counts)}")
    ok &= job["state"] == "done" and counts.get("events_stored", 0) > 0
    accounted = counts.get("events_stored", 0) + counts.get("quarantined", 0)
    ok &= accounted == counts.get("records_read")
    _, quarantine = call("GET", f"{base}/uploads/{accepted['upload_id']}/quarantine?limit=3")
    for item in quarantine["items"]:
        print(f"      record {item['seq']}: {item['reason_code']}: {item['reason']}")

    heading("3. Upload a file with bad records: they are quarantined, not lost")
    no_time = {key: value for key, value in records[1].items() if key != "timestamp"}
    mixed = json.dumps([records[0], no_time, records[2], records[0]]).encode()
    status, accepted = upload(base, "mixed.json", mixed, "fixture")
    job = watch(base, accepted["job_id"], args.timeout)
    print(f"    counts: {json.dumps(job['counts'])}")
    ok &= job["state"] == "done" and (job["counts"] or {}).get("quarantined") == 2
    _, quarantine = call("GET", f"{base}/uploads/{accepted['upload_id']}/quarantine")
    for item in quarantine["items"]:
        print(f"      record {item['seq']}: {item['reason_code']}: {item['reason']}")

    heading("4. Upload for a dataset without a parser yet: a clear failure, never a hang")
    status, accepted = upload(base, "events.json", b"[]", "otrf")
    job = watch(base, accepted["job_id"], args.timeout)
    error = job["error"] or {}
    print(f"    {job['state']}: {error.get('code')}: {error.get('message')}")
    ok &= job["state"] == "failed" and error.get("code") == "no_parser"

    heading("5. Refused at once, nothing stored: wrong file type, empty file")
    for name, content in (("tool.exe", b"MZ"), ("empty.json", b"")):
        status, body = upload(base, name, content, "fixture")
        print(f"    {name}: HTTP {status} {body['error']['code']}: {body['error']['message']}")
        ok &= status in (400, 415)

    heading(
        "Result: " + ("every step behaved as expected" if ok else "SOMETHING FAILED, see above")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
