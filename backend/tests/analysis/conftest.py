import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.analysis import ReportMeta
from app.contracts import EvidencePackage

# Synthetic, masked sample shared with tools/ai1 (not dataset records).
SAMPLES_DIR = Path(__file__).resolve().parents[3] / "tools" / "ai1" / "samples"

META = ReportMeta(
    report_id="rpt-ai1-0001",
    generated_at=datetime(2026, 3, 2, 10, 11, tzinfo=UTC),
    generated_by="hpc",
    model_id="test-model",
)


@pytest.fixture
def evidence() -> EvidencePackage:
    text = (SAMPLES_DIR / "evidence-inc-ai1-0001.json").read_text(encoding="utf-8")
    return EvidencePackage.model_validate_json(text)


@pytest.fixture
def good_output() -> dict:
    """A fresh, mutable copy of the hand-written good output for each test."""
    text = (SAMPLES_DIR / "llm-output-good-inc-ai1-0001.json").read_text(encoding="utf-8")
    return json.loads(text)
