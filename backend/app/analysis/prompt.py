"""Prompts (AI1): the rules every LLM backend sends, and the request built from one package.

Every version stays in `prompts/` so a recorded run can be repeated with the prompt it used.
v1 added two rules after the Week 2 evaluation (docs/ai1-report-schema.md, section 8): a context
event alone never supports the attack story (rule 6), and the attack type is an attack name,
never a claim category (rule 13).
v2 (Week 3, docs/ai1-week3-analysis.md section 3) asks for the five report parts by name (what
happened, how, weaknesses, impact, mitigations) and hardens the prompt against injection: the
package sits between tags that carry an ID the event text cannot guess, tag-like text and chat
special tokens in the package are replaced by "[markup removed]", the rules are repeated after
the package, and rule 14 keeps the rules private. The answer format (LLM output 0.1) is the
same in every version. v2 also has the message for the one schema retry (`repair_messages`).
"""

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.analysis.output import LlmOutput
from app.contracts import EvidencePackage

PROMPT_VERSION = "ai1-prompt-v2"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# version -> (system template, user template)
PROMPT_FILES = {
    "ai1-prompt-v0": ("system_v0.txt", "user_v0.txt"),
    "ai1-prompt-v1": ("system_v1.txt", "user_v0.txt"),
    "ai1-prompt-v2": ("system_v2.txt", "user_v2.txt"),
}
# Versions that fence the package with an ID and remove markup from it.
HARDENED_VERSIONS = {"ai1-prompt-v2"}
REPAIR_FILE = "repair_v2.txt"
MARKUP_REMOVED = "[markup removed]"
# How many problem lines the retry message shows the model at most.
MAX_REPAIR_LINES = 20

# The model gets the package without its storage fields (contracts-v1 section 8, question 1).
HIDDEN_PACKAGE_FIELDS = {"schema_version", "package_id", "masked"}

# Text in event fields that could end the package early or pose as a chat turn: tags named like
# the fence or a chat role, and the special tokens of common chat templates (ChatML, Llama,
# Mistral, Gemma). Everything else in the event text stays as the log recorded it.
MARKUP = re.compile(
    r"</?\s*(?:evidence[\s_-]*package|system|assistant|user|developer|tool|instructions?)\b[^>]{0,200}>"
    r"|<\|[^|<>\n]{1,40}\|>"
    r"|\[/?INST\]|<</?SYS>>"
    r"|<(?:start|end)_of_turn>",
    re.IGNORECASE,
)


def _template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def fence_id(evidence: EvidencePackage) -> str:
    """The ID on the package tags: fixed per package, so the prompt (and the cache) is stable,
    but not written anywhere in the event text the model reads."""
    return hashlib.sha256(f"fence:{evidence.package_id}".encode()).hexdigest()[:16]


def neutralize(value: Any) -> tuple[Any, int]:
    """A copy of a JSON value with markup in its strings replaced; and how many were replaced."""
    if isinstance(value, str):
        return MARKUP.subn(MARKUP_REMOVED, value)
    if isinstance(value, list):
        items = [neutralize(item) for item in value]
        return [item for item, _ in items], sum(n for _, n in items)
    if isinstance(value, dict):
        pairs = {key: neutralize(item) for key, item in value.items()}
        return {key: item for key, (item, _) in pairs.items()}, sum(n for _, n in pairs.values())
    return value, 0


def model_package(evidence: EvidencePackage, version: str = PROMPT_VERSION) -> dict:
    """The package as the model sees it: no storage fields; markup removed for hardened prompts."""
    package = evidence.model_dump(mode="json", exclude=HIDDEN_PACKAGE_FIELDS)
    if version in HARDENED_VERSIONS:
        package, _ = neutralize(package)
    return package


def build_messages(
    evidence: EvidencePackage, version: str = PROMPT_VERSION
) -> list[dict[str, str]]:
    """Chat messages for one package: the system rules and the user request."""
    system_file, user_file = PROMPT_FILES[version]
    package = model_package(evidence, version)
    user = (
        _template(user_file)
        .replace("{{output_schema}}", json.dumps(LlmOutput.model_json_schema(), indent=1))
        .replace("{{fence}}", fence_id(evidence))
        .replace("{{evidence_package}}", json.dumps(package, indent=1))
    )
    return [
        {"role": "system", "content": _template(system_file)},
        {"role": "user", "content": user},
    ]


def repair_messages(
    messages: Sequence[dict[str, str]], answer: str, problems: Sequence[str]
) -> list[dict[str, str]]:
    """The conversation for the one schema retry: the first request, the model's answer, and
    what was wrong with it. Only parse, schema and contract errors are shown (never evidence)."""
    shown = list(problems)[:MAX_REPAIR_LINES]
    if len(problems) > MAX_REPAIR_LINES:
        shown.append(f"... and {len(problems) - MAX_REPAIR_LINES} more")
    text = _template(REPAIR_FILE).replace("{{problems}}", "\n".join(f"- {p}" for p in shown))
    return [
        *messages,
        {"role": "assistant", "content": answer},
        {"role": "user", "content": text},
    ]
