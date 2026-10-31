"""The Docker image only holds backend/app, so the app keeps copies of two contracts files."""

from pathlib import Path

import pytest

from app.ingest.event_types import EVENT_TYPES
from app.ingest.labels import LABEL_MAPPING

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


@pytest.mark.parametrize("packaged", [LABEL_MAPPING, EVENT_TYPES], ids=lambda p: p.name)
def test_packaged_copy_equals_contracts_file(packaged):
    original = CONTRACTS / packaged.name
    assert packaged.read_bytes() == original.read_bytes(), (
        f"Copy contracts/{packaged.name} to backend/app/ingest/mappings/ after editing it."
    )
