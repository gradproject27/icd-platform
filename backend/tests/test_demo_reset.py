"""C1 demo reset (decision F9): empties the app tables and uploads, keeps the schema."""

import os

import pytest
from sqlalchemy import text

from app.db import get_engine
from app.demo import reset as demo_reset


@pytest.fixture(autouse=True)
def _needs_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")


def test_reset_refuses_without_the_flag(monkeypatch, capsys):
    monkeypatch.delenv("ICD_ALLOW_RESET", raising=False)
    assert demo_reset.main() == 2
    assert "refused" in capsys.readouterr().err


def test_reset_empties_tables_and_uploads_but_keeps_the_schema(tmp_path):
    engine = get_engine()
    with engine.begin() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        connection.execute(
            text(
                "INSERT INTO uploads (upload_id, dataset_id, filename, size_bytes, sha256,"
                " received_at) VALUES ('upl-reset', 'fixture', 'x.json', 1, repeat('0', 64),"
                " now())"
            )
        )
    (tmp_path / "upl-reset").write_text("{}")

    tables, deleted = demo_reset.reset(engine, tmp_path)

    assert "uploads" in tables and "alembic_version" not in tables
    assert deleted == 1 and not any(tmp_path.iterdir())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM uploads")) == 0
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == version
