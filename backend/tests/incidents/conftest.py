import os

import pytest
from sqlalchemy import text

from app.db import get_engine


@pytest.fixture(autouse=True)
def _needs_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")


@pytest.fixture
def engine():
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE incident_events, incidents, quarantined_records, events, jobs, uploads "
                "RESTART IDENTITY CASCADE"
            )
        )
    return engine
