from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.ingest.interface import IntakeContext

SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "ingest" / "unsw-nb15-sample.csv"
INGESTED_AT = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


@pytest.fixture
def sample() -> Path:
    """30 synthetic UNSW-NB15-shaped lines, documentation IPs only (fixtures/ingest/README.md)."""
    return SAMPLE


@pytest.fixture
def context():
    def make(source_file: str = "UNSW-NB15_1.csv") -> IntakeContext:
        return IntakeContext(
            upload_id="upl-test",
            dataset_id="unsw-nb15",
            source_file=source_file,
            ingested_at=INGESTED_AT,
        )

    return make
