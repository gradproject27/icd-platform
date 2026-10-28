import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_engine
from app.main import app
from app.settings import get_settings

FIXTURE_EVENTS = Path(__file__).resolve().parents[3] / "fixtures" / "correlation" / "events.json"


@pytest.fixture(autouse=True)
def _needs_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")


@pytest.fixture
def fixture_events() -> Path:
    """The C3 correlation fixture: 37 Events, 18 flagged, 17 unflagged, 2 unlabelled."""
    return FIXTURE_EVENTS


@pytest.fixture
def engine():
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE quarantined_records, events, jobs, uploads RESTART IDENTITY CASCADE")
        )
    return engine


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("WORKER_HEARTBEAT_SECONDS", "0.05")
    monkeypatch.setenv("WORKER_LEASE_SECONDS", "60")
    return get_settings()


@pytest.fixture
def client(engine, settings):
    return TestClient(app)


@pytest.fixture
def upload(client):
    """POST a file and return the 202 body."""

    def post(content: bytes, name: str = "events.json", dataset_id: str = "fixture") -> dict:
        response = client.post(
            "/uploads", data={"dataset_id": dataset_id}, files={"file": (name, content)}
        )
        assert response.status_code == 202, response.text
        return response.json()

    return post
