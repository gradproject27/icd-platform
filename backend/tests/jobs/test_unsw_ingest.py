"""M2 for C2: an UNSW-NB15 upload gives labelled, queryable events linked to their lines."""

from pathlib import Path

from app.api.schemas import EventPage, Job, QuarantinePage
from app.ingest.lines import read_original
from app.jobs.queue import utcnow
from app.worker.runner import run_once

SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "ingest" / "unsw-nb15-sample.csv"


def test_unsw_upload_gives_labelled_queryable_events(upload, client, engine, settings):
    accepted = upload(SAMPLE.read_bytes(), name="UNSW-NB15_1.csv", dataset_id="unsw-nb15")
    assert run_once(engine, "worker-test", settings, utcnow) is True

    done = Job.model_validate(client.get(f"/jobs/{accepted['job_id']}").json())
    assert done.state == "done"
    assert done.counts.model_dump() == {
        "records_read": 30,
        "events_stored": 23,
        "flagged": 13,
        "unflagged": 9,
        "unlabelled": 1,
        "quarantined": 7,
        "quarantined_by_reason": {
            "bad_timestamp": 2,
            "empty_record": 1,
            "missing_timestamp": 1,
            "unknown_label": 2,
            "wrong_column_count": 1,
        },
    }

    base = f"/uploads/{accepted['upload_id']}"
    unlabelled = EventPage.model_validate(
        client.get(f"{base}/events?label_status=unlabelled").json()
    )
    assert [event.event_id for event in unlabelled.items] == ["unsw-nb15:UNSW-NB15_1:22"]
    assert unlabelled.items[0].label.raw_value is None

    flagged = EventPage.model_validate(
        client.get(f"{base}/events?label_status=flagged&limit=500").json()
    )
    assert len(flagged.items) == 13
    stored = settings.upload_dir / accepted["upload_id"]
    for event in flagged.items:
        line = read_original(stored, event.provenance.record_ref)
        assert line.endswith(",1") and line.startswith(str(event.src_ip))

    quarantine = QuarantinePage.model_validate(client.get(f"{base}/quarantine").json())
    assert [item.seq for item in quarantine.items] == [23, 24, 25, 26, 27, 28, 29]
    assert quarantine.items[0].record_ref == "UNSW-NB15_1.csv:23"
