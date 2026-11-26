"""Opinion prompt (AI1): one short yes/no question per evidence group, separate from the report.

The report prompt (app/analysis/prompt.py) writes the analyst's report after the final score;
this one only answers "is this group a real attack?" for C3's event confidence (design note
section 9A.2, step 3). It keeps the report prompt's injection hardening: the group sits between
tags whose ID the event text cannot guess, and tag-like text and chat tokens are already
replaced in the view (`app.opinion.view` runs `neutralize`).
"""

import hashlib
import json
from pathlib import Path

from app.opinion.view import GroupView

OPINION_PROMPT_VERSION = "ai1-opinion-v1"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES = {"ai1-opinion-v1": ("opinion_system_v1.txt", "opinion_user_v1.txt")}


def _template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def view_text(view: GroupView) -> str:
    """The view as sent: sorted keys, so the same group always gives the same prompt."""
    return json.dumps(view.document, indent=1, sort_keys=True, ensure_ascii=False)


def fence_id(view: GroupView) -> str:
    return hashlib.sha256(f"opinion-fence:{view_text(view)}".encode()).hexdigest()[:16]


def build_messages(view: GroupView, version: str = OPINION_PROMPT_VERSION) -> list[dict[str, str]]:
    system_file, user_file = PROMPT_FILES[version]
    user = (
        _template(user_file)
        .replace("{{fence}}", fence_id(view))
        .replace("{{group}}", view_text(view))
    )
    return [
        {"role": "system", "content": _template(system_file)},
        {"role": "user", "content": user},
    ]
