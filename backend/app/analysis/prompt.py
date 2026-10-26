"""Prompt v0 (AI1): the rules every LLM backend sends, and the request built from one package."""

import json
from pathlib import Path

from app.analysis.output import LlmOutput
from app.contracts import EvidencePackage

PROMPT_VERSION = "ai1-prompt-v0"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# The model gets the package without its storage fields (contracts-v1 section 8, question 1).
HIDDEN_PACKAGE_FIELDS = {"schema_version", "package_id", "masked"}


def _template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_messages(evidence: EvidencePackage) -> list[dict[str, str]]:
    """Chat messages for one package: the system rules and the user request."""
    package = evidence.model_dump(mode="json", exclude=HIDDEN_PACKAGE_FIELDS)
    user = (
        _template("user_v0.txt")
        .replace("{{output_schema}}", json.dumps(LlmOutput.model_json_schema(), indent=1))
        .replace("{{evidence_package}}", json.dumps(package, indent=1))
    )
    return [
        {"role": "system", "content": _template("system_v0.txt")},
        {"role": "user", "content": user},
    ]
