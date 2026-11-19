"""Prompts (AI1): the rules every LLM backend sends, and the request built from one package.

Every version stays in `prompts/` so a recorded run can be repeated with the prompt it used.
v1 adds two rules after the Week 2 evaluation (docs/ai1-report-schema.md, section 8): a context
event alone never supports the attack story (rule 6), and the attack type is an attack name,
never a claim category (rule 13). It met every metric on the cluster model and fixed the
attack-type fault of the small one, so the app sends v1; v0 stays for repeating recorded runs.
"""

import json
from pathlib import Path

from app.analysis.output import LlmOutput
from app.contracts import EvidencePackage

PROMPT_VERSION = "ai1-prompt-v1"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# version -> (system template, user template)
PROMPT_FILES = {
    "ai1-prompt-v0": ("system_v0.txt", "user_v0.txt"),
    "ai1-prompt-v1": ("system_v1.txt", "user_v0.txt"),
}

# The model gets the package without its storage fields (contracts-v1 section 8, question 1).
HIDDEN_PACKAGE_FIELDS = {"schema_version", "package_id", "masked"}


def _template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def build_messages(
    evidence: EvidencePackage, version: str = PROMPT_VERSION
) -> list[dict[str, str]]:
    """Chat messages for one package: the system rules and the user request."""
    system_file, user_file = PROMPT_FILES[version]
    package = evidence.model_dump(mode="json", exclude=HIDDEN_PACKAGE_FIELDS)
    user = (
        _template(user_file)
        .replace("{{output_schema}}", json.dumps(LlmOutput.model_json_schema(), indent=1))
        .replace("{{evidence_package}}", json.dumps(package, indent=1))
    )
    return [
        {"role": "system", "content": _template(system_file)},
        {"role": "user", "content": user},
    ]
