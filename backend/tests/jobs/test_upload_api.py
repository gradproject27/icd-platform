import hashlib
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import DatasetList, ErrorResponse, Job, Upload, UploadAccepted
from app.models import JobRow, UploadRow

FIXTURE_EVENTS = Path(__file__).resolve().parents[3] / "fixtures" / "correlation" / "events.json"


def rows(engine, model) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert ErrorResponse.model_validate(response.json()).error.code == code


def test_datasets_list_every_source_and_the_limit(client, settings):
    body = DatasetList.model_validate(client.get("/datasets").json())
    available = {item.dataset_id.value: item.parser_available for item in body.items}
    assert available["fixture"] is True
    assert available["unsw-nb15"] is True
    assert available["otrf"] is False
    assert body.max_upload_bytes == settings.max_upload_bytes


def test_upload_answers_202_at_once_with_a_queued_job(client, engine, settings):
    content = FIXTURE_EVENTS.read_bytes()
    response = client.post(
        "/uploads",
        data={"dataset_id": "fixture"},
        files={"file": ("events.json", content, "application/json")},
    )
    assert response.status_code == 202
    accepted = UploadAccepted.model_validate(response.json())
    assert response.headers["location"] == accepted.status_url == f"/jobs/{accepted.job_id}"

    # Nothing is processed in the request: the job waits for the worker.
    job = Job.model_validate(client.get(accepted.status_url).json())
    assert (job.state, job.kind, job.upload_id, job.attempts) == (
        "queued",
        "ingest",
        accepted.upload_id,
        0,
    )
    upload = Upload.model_validate(client.get(f"/uploads/{accepted.upload_id}").json())
    assert upload.sha256 == hashlib.sha256(content).hexdigest()
    assert (upload.size_bytes, upload.filename, upload.job_id) == (
        len(content),
        "events.json",
        accepted.job_id,
    )
    stored = settings.upload_dir / accepted.upload_id
    assert stored.read_bytes() == content
    assert sorted(p.name for p in settings.upload_dir.iterdir()) == [accepted.upload_id]


def test_file_name_is_never_used_as_a_path(upload, client, settings):
    accepted = upload(b"[]", name="..\\..\\..\\windows\\evil.json")
    assert client.get(f"/uploads/{accepted['upload_id']}").json()["filename"] == "evil.json"
    assert [p.name for p in settings.upload_dir.iterdir()] == [accepted["upload_id"]]


def test_unknown_dataset_is_refused(client, engine):
    response = client.post(
        "/uploads", data={"dataset_id": "my-data"}, files={"file": ("a.csv", b"x")}
    )
    assert_error(response, 422, "dataset_unknown")
    assert rows(engine, UploadRow) == 0


def test_missing_field_is_a_validation_error(client):
    response = client.post("/uploads", files={"file": ("a.csv", b"x")})
    assert_error(response, 422, "validation_error")
    assert "dataset_id" in response.json()["error"]["message"]


def test_format_not_accepted(client, engine, settings):
    response = client.post(
        "/uploads", data={"dataset_id": "fixture"}, files={"file": ("tool.exe", b"MZ")}
    )
    assert_error(response, 415, "format_not_accepted")
    assert ".exe" in response.json()["error"]["message"]
    assert rows(engine, UploadRow) == 0
    assert not settings.upload_dir.exists() or not any(settings.upload_dir.iterdir())


def test_empty_file_stores_nothing(client, engine, settings):
    response = client.post(
        "/uploads", data={"dataset_id": "fixture"}, files={"file": ("e.json", b"")}
    )
    assert_error(response, 400, "file_empty")
    assert rows(engine, UploadRow) == rows(engine, JobRow) == 0
    assert not any(settings.upload_dir.iterdir())


def test_too_large_while_streaming_stores_nothing(client, engine, monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_UPLOAD_MB", str(10 / (1024 * 1024)))  # 10 bytes
    response = client.post(
        "/uploads", data={"dataset_id": "fixture"}, files={"file": ("e.json", b"x" * 20)}
    )
    assert_error(response, 413, "file_too_large")
    assert rows(engine, UploadRow) == 0
    assert not any((tmp_path / "uploads").iterdir())


def test_too_large_by_content_length_is_refused_before_reading(client, engine, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", str(10 / (1024 * 1024)))
    response = client.post(
        "/uploads", data={"dataset_id": "fixture"}, files={"file": ("e.json", b"x" * 200_000)}
    )
    assert_error(response, 413, "file_too_large")
    assert rows(engine, UploadRow) == 0


def test_unknown_ids_are_404_with_the_error_shape(client):
    assert_error(client.get("/jobs/job-nope"), 404, "not_found")
    assert_error(client.get("/uploads/upl-nope"), 404, "not_found")
    assert_error(client.get("/uploads/upl-nope/events"), 404, "not_found")
    assert_error(client.get("/uploads/upl-nope/quarantine"), 404, "not_found")


def test_page_limit_is_checked(upload, client):
    accepted = upload(b"[]")
    response = client.get(f"/uploads/{accepted['upload_id']}/events?limit=501")
    assert_error(response, 422, "validation_error")


# Duplicate-upload guard (C2, decided 16 Nov 2026): same SHA-256 and dataset, earlier upload
# not failed -> 409 duplicate_upload pointing to the earlier upload; nothing is stored.


def post(client, content: bytes, dataset_id: str = "fixture"):
    return client.post(
        "/uploads", data={"dataset_id": dataset_id}, files={"file": ("events.json", content)}
    )


def test_same_file_again_is_refused_and_points_to_the_first(client, engine, settings):
    content = FIXTURE_EVENTS.read_bytes()
    first = UploadAccepted.model_validate(post(client, content).json())
    response = post(client, content)
    assert_error(response, 409, "duplicate_upload")
    assert response.headers["location"] == f"/uploads/{first.upload_id}"
    assert first.upload_id in response.json()["error"]["message"]
    assert rows(engine, UploadRow) == rows(engine, JobRow) == 1
    assert [p.name for p in settings.upload_dir.iterdir()] == [first.upload_id]


def test_same_file_for_another_dataset_is_accepted(client, engine):
    assert post(client, b"[]").status_code == 202
    assert post(client, b"[]", dataset_id="unsw-nb15").status_code == 202
    assert rows(engine, UploadRow) == 2


def test_different_file_is_accepted(client, engine):
    assert post(client, b"[]").status_code == 202
    assert post(client, b"[ ]").status_code == 202
    assert rows(engine, UploadRow) == 2


def test_retry_after_a_failed_upload_is_accepted(client, engine):
    first = post(client, b"[]").json()
    with Session(engine) as session, session.begin():
        session.get(JobRow, first["job_id"]).state = "failed"
    second = post(client, b"[]")
    assert second.status_code == 202, second.text
    assert second.json()["upload_id"] != first["upload_id"]
    # The new upload is not failed, so a third copy is refused and points to it.
    third = post(client, b"[]")
    assert_error(third, 409, "duplicate_upload")
    assert third.headers["location"] == f"/uploads/{second.json()['upload_id']}"


def test_two_identical_uploads_at_once_accept_exactly_one(client, engine):
    from concurrent.futures import ThreadPoolExecutor

    content = b'[{"x": 1}]'
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(pool.map(lambda _: post(client, content).status_code, range(4)))
    assert codes == [202, 409, 409, 409]
    assert rows(engine, UploadRow) == 1
