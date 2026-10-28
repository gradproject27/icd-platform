import json
from pathlib import Path

from app.api.schemas import Job, QuarantinePage

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "fixtures" / "correlation" / "events.json").read_text(
        encoding="utf-8"
    )
)


def test_nul_character_is_quarantined_not_a_failed_job(upload, client, engine, settings):
    from app.jobs.queue import utcnow
    from app.worker.runner import run_once

    with_nul = {**FIXTURE[1], "summary": "bad\u0000summary"}
    bad_record = {**FIXTURE[2], "timestamp": None, "summary": "x\u0000y"}
    content = json.dumps([FIXTURE[0], with_nul, bad_record]).encode()
    accepted = upload(content, name="nul.json")
    run_once(engine, "worker-test", settings, utcnow)

    job = Job.model_validate(client.get(f"/jobs/{accepted['job_id']}").json())
    assert job.state == "done", job.error
    assert job.counts.events_stored == 1
    assert job.counts.quarantined_by_reason == {"invalid_event": 1, "nul_character": 1}
    page = QuarantinePage.model_validate(
        client.get(f"/uploads/{accepted['upload_id']}/quarantine").json()
    )
    assert all("\x00" not in (item.raw_excerpt or "") for item in page.items)
