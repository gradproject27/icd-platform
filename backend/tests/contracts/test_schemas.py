import json
from pathlib import Path

import pytest

from app.contracts import AnalysisReport, EvidencePackage, Incident
from app.contracts.export import CONTRACTS, schema_text
from app.llm.adapter import uncited_event_ids

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"


def read(kind: str, name: str) -> str:
    return (CONTRACTS_DIR / f"{kind}s" / f"{name}.{kind}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", CONTRACTS)
def test_committed_schema_is_up_to_date(name):
    path = CONTRACTS_DIR / "schemas" / f"{name}.schema.json"
    committed = path.read_text(encoding="utf-8") if path.exists() else ""
    assert committed == schema_text(CONTRACTS[name]), (
        f"contracts/schemas/{path.name} is out of date. Run `python -m app.contracts.export` "
        "from backend/ and commit the result."
    )


@pytest.mark.parametrize("name", CONTRACTS)
def test_example_keys_match_schema(name):
    schema = json.loads(read("schema", name))
    example = json.loads(read("example", name))
    assert set(example) <= set(schema["properties"])
    assert set(schema["required"]) <= set(example)


def test_example_story_is_consistent():
    incident = Incident.model_validate_json(read("example", "incident"))
    package = EvidencePackage.model_validate_json(read("example", "evidence-package"))
    report = AnalysisReport.model_validate_json(read("example", "analysis-report"))
    assert package.incident_id == incident.incident_id
    assert report.incident_id == incident.incident_id
    assert report.evidence_package_id == package.package_id
    assert report.report_id == incident.latest_report_id
    assert uncited_event_ids(report, package) == []
    assert package.citable_event_ids() == {link.event_id for link in incident.events}
    for name in ("response-action", "audit-record"):
        assert json.loads(read("example", name))["incident_id"] == incident.incident_id
