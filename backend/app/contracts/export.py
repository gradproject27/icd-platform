"""Write the JSON Schemas of the six contracts to contracts/schemas/ at the repo root.

Run from backend/: python -m app.contracts.export
"""

import json
from pathlib import Path

from pydantic import BaseModel

from app.contracts import (
    AnalysisReport,
    AuditRecord,
    Event,
    EvidencePackage,
    Incident,
    ResponseAction,
)

CONTRACTS: dict[str, type[BaseModel]] = {
    "event": Event,
    "incident": Incident,
    "evidence-package": EvidencePackage,
    "analysis-report": AnalysisReport,
    "response-action": ResponseAction,
    "audit-record": AuditRecord,
}

# The repo root's contracts/ folder: works from a repo checkout, not inside the api container.
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "contracts" / "schemas"


def schema_text(model: type[BaseModel]) -> str:
    """The exact file content for a model's schema, identical on Windows and Linux."""
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in CONTRACTS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(schema_text(model))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
