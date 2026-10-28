"""Write the JSON Schemas of the API shapes to docs/api/schemas/ at the repo root.

Run from backend/: python -m app.api.export
"""

from pathlib import Path

from pydantic import BaseModel

from app.api.schemas import (
    DatasetList,
    ErrorResponse,
    EventPage,
    Job,
    JobAccepted,
    QuarantinePage,
    Upload,
    UploadAccepted,
)
from app.contracts.export import schema_text

SHAPES: dict[str, type[BaseModel]] = {
    "dataset-list": DatasetList,
    "upload-accepted": UploadAccepted,
    "upload": Upload,
    "job-accepted": JobAccepted,
    "job": Job,
    "event-page": EventPage,
    "quarantine-page": QuarantinePage,
    "error-response": ErrorResponse,
}

# The repo root's docs/api/schemas/ folder: works from a repo checkout only.
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "api" / "schemas"


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in SHAPES.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(schema_text(model))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
