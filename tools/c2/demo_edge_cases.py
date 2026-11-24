"""Demo slice and the two ingestion edge cases, against a running stack (C2, Week 4; C2-D19).

    docker compose up --build --detach --wait
    python tools/c2/demo_edge_cases.py demo/unsw-nb15-demo-slice.csv
    python tools/c2/demo_edge_cases.py demo/unsw-nb15-demo-slice.csv --base-url http://localhost:8000

Checks, in order (standard library only; prints counts, levels and reason codes, never rows):
1. The demo slice uploads, every line becomes an event, and its incidents have the levels the
   committed manifest expects (at least one High and one Medium).
2. Uploading the same file again is refused: 409 duplicate_upload naming the first upload.
3. The slice with three malformed lines appended is accepted as a new file; exactly those
   three lines are quarantined with a reason and every other line is stored.
"""

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "fixtures" / "demo" / "unsw-nb15-demo-slice.json"
# Three malformed lines and the reason each must get (docs/ingestion.md, C2 decision D11).
MALFORMED = (
    (b"1,2,3\n", "wrong_column_count"),
    (b"\n", "empty_record"),
    (None, "bad_timestamp"),  # built from the slice's first line with Stime = not-a-time
)
STIME = 28  # 0-based column of Stime in the 49-column layout


def call(method: str, url: str, body: bytes | None = None, content_type: str | None = None):
    request = urllib.request.Request(url, data=body, method=method)
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def upload(base: str, name: str, content: bytes):
    boundary = uuid.uuid4().hex
    body = b"".join(
        [
            f'--{boundary}\r\nContent-Disposition: form-data; name="dataset_id"\r\n\r\n'
            "unsw-nb15\r\n".encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: text/csv\r\n\r\n".encode()
            + content
            + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return call("POST", f"{base}/uploads", body, f"multipart/form-data; boundary={boundary}")


def wait(base: str, job_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        _, job = call("GET", f"{base}/jobs/{job_id}")
        if job["state"] in ("done", "failed") or time.monotonic() > deadline:
            return job
        time.sleep(1)


def check(ok: bool, text: str) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}")
    return ok


def malformed_lines(content: bytes) -> bytes:
    first = content.split(b"\n", 1)[0].rstrip(b"\r").split(b",")
    first[STIME] = b"not-a-time"
    lines = [line if line is not None else b",".join(first) + b"\n" for line, _ in MALFORMED]
    return b"".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slice", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8080/api")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    content = args.slice.read_bytes()
    ok = True

    print("1. Upload the demo slice")
    digest = hashlib.sha256(content).hexdigest()
    ok &= check(digest == manifest["slice_sha256"], f"slice sha256 matches ({digest[:12]}…)")
    status, accepted = upload(base, args.slice.name, content)
    if status == 409:
        print("  the stack already has this slice; reset the stack first (docker compose down -v)")
        return 1
    ok &= check(status == 202, f"POST /uploads -> {status}")
    print(f"  slice upload_id: {accepted['upload_id']}")
    job = wait(base, accepted["job_id"], args.timeout)
    counts = job.get("counts") or {}
    ok &= check(job["state"] == "done", f"job {job['state']}; counts {json.dumps(counts)}")
    ok &= check(
        counts.get("events_stored") == manifest["lines"] and counts.get("quarantined") == 0,
        f"{manifest['lines']:,} lines -> {counts.get('events_stored')} events, 0 quarantined",
    )
    _, listed = call("GET", f"{base}/incidents?upload_id={accepted['upload_id']}")
    levels = Counter((item["incident"].get("risk") or {}).get("level") for item in listed["items"])
    ok &= check(
        dict(sorted(levels.items())) == manifest["levels"],
        f"incident levels {dict(levels)} (manifest {manifest['levels']})",
    )
    ok &= check(levels["high"] >= 1 and levels["medium"] >= 1, "at least one High and one Medium")

    print("2. Upload the same file again")
    status, body = upload(base, args.slice.name, content)
    error = (body or {}).get("error") or {}
    ok &= check(
        status == 409 and error.get("code") == "duplicate_upload"
        and accepted["upload_id"] in error.get("message", ""),
        f"-> {status} {error.get('code')}, names the first upload",
    )  # fmt: skip

    print("3. Upload the slice with three malformed lines appended")
    broken = content + malformed_lines(content)
    status, accepted = upload(base, "unsw-nb15-demo-slice-malformed.csv", broken)
    ok &= check(status == 202, f"POST /uploads -> {status} (a different file, so not a duplicate)")
    job = wait(base, accepted["job_id"], args.timeout)
    counts = job.get("counts") or {}
    ok &= check(
        job["state"] == "done"
        and counts.get("quarantined") == len(MALFORMED)
        and counts.get("events_stored") == manifest["lines"],
        f"job {job['state']}; counts {json.dumps(counts)}",
    )  # fmt: skip
    _, page = call("GET", f"{base}/uploads/{accepted['upload_id']}/quarantine")
    reasons = sorted(item["reason_code"] for item in page["items"])
    ok &= check(
        reasons == sorted(reason for _, reason in MALFORMED), f"quarantine reasons {reasons}"
    )

    print("ALL PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
