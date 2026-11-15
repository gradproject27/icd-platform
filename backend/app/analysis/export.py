"""Write AI1's JSON Schemas to contracts/ai1/ at the repo root.

Run from backend/: python -m app.analysis.export
These are AI1's own formats, not shared contracts: the LLM output the model returns, the HPC
output file, and the expected-incident file of the evaluation (docs/ai1-report-schema.md).
"""

from pathlib import Path

from pydantic import BaseModel

from app.analysis.handoff import HpcOutput
from app.analysis.metrics import ExpectedIncident
from app.analysis.output import LlmOutput
from app.contracts.export import schema_text

SCHEMAS: dict[str, type[BaseModel]] = {
    "llm-output-v0": LlmOutput,
    "hpc-output-v1": HpcOutput,
    "expected-incident-v1": ExpectedIncident,
}

# Works from a repo checkout, not inside the api container.
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "contracts" / "ai1"


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(schema_text(model))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
