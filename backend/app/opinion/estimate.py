"""One evidence group -> one GroupOpinion (AI1, risk-v1 step 4).

    view (masked, label-blind) -> prompt -> n answers -> p_raw -> calibrator -> p_llm

Methods (proposed decision AI1-OP-D2):
- samples (default): n answers at temperature > 0; p_raw = share of "yes" among valid answers.
  At least `min_valid` answers must parse, else the opinion fails (AI1-OP-D3).
- logprob: one answer at temperature 0 with token probabilities; p_raw = P(yes) at the answer
  token. It fails if the server gives no token probabilities, or if they disagree with the
  answer that was written (the token found was not the answer).

A failure is never turned into a value: the opinion has status "failed" and no p_raw, and C3
keeps the classifier-only score with flag llm_unavailable (RV1-D3).

Cache: only the model's answer is cached (counts, p_raw, reasons), keyed by the view, prompt,
model and settings. The calibrator is applied after the cache, so a new calibrator never calls
the model again (design note 9A.3: stored opinions are re-used when re-scoring).
"""

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.analysis.backends import BackendError
from app.contracts import Event, Incident
from app.opinion.calibration import Calibrator
from app.opinion.client import OpinionClient
from app.opinion.groups import OpinionGroup, incident_groups
from app.opinion.models import OPINION_FORMAT, GroupOpinion, OpinionMethod
from app.opinion.prompt import OPINION_PROMPT_VERSION, build_messages, view_text
from app.opinion.view import MAX_VIEW_EVENTS, build_view

MAX_REASONS = 5
MAX_REASON_CHARS = 300
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


@dataclass(frozen=True)
class OpinionSettings:
    method: OpinionMethod = "samples"
    samples: int = 5
    temperature: float = 0.7
    min_valid: int = 3
    prompt_version: str = OPINION_PROMPT_VERSION
    view_cap: int = MAX_VIEW_EVENTS

    def __post_init__(self) -> None:
        if self.method == "logprob" and (self.samples != 1 or self.min_valid != 1):
            raise ValueError("logprob uses one answer: samples=1, min_valid=1")
        if not 1 <= self.min_valid <= self.samples:
            raise ValueError("min_valid must be 1 to samples")
        if self.temperature < 0:
            raise ValueError("temperature must be >= 0")

    @classmethod
    def logprob(cls) -> "OpinionSettings":
        return cls(method="logprob", samples=1, temperature=0.0, min_valid=1)


class CachedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    samples_valid: int = Field(ge=0)
    yes_count: int = Field(ge=0)
    p_raw: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class OpinionCache(Protocol):
    def get(self, key: str) -> CachedAnswer | None: ...

    def put(self, entry: CachedAnswer) -> None: ...


class MemoryOpinionCache:
    def __init__(self) -> None:
        self.entries: dict[str, CachedAnswer] = {}

    def get(self, key: str) -> CachedAnswer | None:
        return self.entries.get(key)

    def put(self, entry: CachedAnswer) -> None:
        self.entries[entry.key] = entry


class FileOpinionCache:
    """<root>/<first 2 hex digits>/<key>.json, like the report cache."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path(self, key: str) -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("a cache key is 64 lower-case hex digits")
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> CachedAnswer | None:
        path = self.path(key)
        if not path.exists():
            return None
        entry = CachedAnswer.model_validate_json(path.read_text(encoding="utf-8"))
        return entry if entry.key == key else None

    def put(self, entry: CachedAnswer) -> None:
        path = self.path(entry.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(entry.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def cache_key(view: str, settings: OpinionSettings, model_id: str) -> str:
    document = {
        "format": OPINION_FORMAT,
        "view": view,
        "prompt_version": settings.prompt_version,
        "model": model_id,
        "method": settings.method,
        "samples": settings.samples,
        "temperature": settings.temperature,
    }
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_answer(text: str) -> tuple[bool | None, str | None]:
    """(True for yes, False for no, None if unreadable; the reason or None)."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None, None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    answer = data.get("answer")
    answer = answer.strip().lower() if isinstance(answer, str) else None
    reason = data.get("reason")
    reason = (
        reason.strip()[:MAX_REASON_CHARS] if isinstance(reason, str) and reason.strip() else None
    )
    if answer == "yes":
        return True, reason
    if answer == "no":
        return False, reason
    return None, reason


def check_calibrator(calibrator: Calibrator, settings: OpinionSettings, model_id: str) -> None:
    """A calibrator fitted for another method, prompt or model must never be applied."""
    expected = (settings.method, settings.prompt_version, model_id)
    actual = (calibrator.method, calibrator.prompt_version, calibrator.model_id)
    if expected != actual:
        raise ValueError(f"calibrator {calibrator.version} was fitted for {actual}, not {expected}")


def _ask(
    messages: list[dict[str, str]], client: OpinionClient, settings: OpinionSettings
) -> tuple[int, int, float | None, list[str], str | None]:
    """(valid, yes, p_raw, reasons, failure)."""
    try:
        samples = client.ask(
            messages,
            n=settings.samples,
            temperature=settings.temperature,
            logprobs=settings.method == "logprob",
        )
    except BackendError as exc:
        return 0, 0, None, [], f"backend_error: {exc}"
    parsed = [parse_answer(s.text) for s in samples]
    valid = [answer for answer, _ in parsed if answer is not None]
    yes = sum(1 for answer in valid if answer)
    reasons = list(dict.fromkeys(r for _, r in parsed if r))[:MAX_REASONS]
    if len(valid) < settings.min_valid:
        return (
            len(valid),
            yes,
            None,
            reasons,
            (f"too_few_valid_answers: {len(valid)} of {len(samples)}, need {settings.min_valid}"),
        )
    if settings.method == "samples":
        return len(valid), yes, yes / len(valid), reasons, None
    p_yes = samples[0].yes_probability
    if p_yes is None:
        return (
            len(valid),
            yes,
            None,
            reasons,
            "no_logprobs: the server gave no answer-token probability",
        )
    if (p_yes >= 0.5) != bool(valid[0]) and settings.temperature == 0:
        return len(valid), yes, None, reasons, "logprob_answer_mismatch"
    return len(valid), yes, p_yes, reasons, None


def estimate(
    group: OpinionGroup,
    client: OpinionClient,
    settings: OpinionSettings | None = None,
    calibrator: Calibrator | None = None,
    cache: OpinionCache | None = None,
) -> GroupOpinion:
    settings = settings or OpinionSettings()
    if calibrator is not None:
        check_calibrator(calibrator, settings, client.model_id)
    view = build_view(group, settings.view_cap)
    key = cache_key(view_text(view), settings, client.model_id)

    cached = cache.get(key) if cache is not None else None
    if cached is not None:
        valid, yes, p_raw, reasons, failure = (
            cached.samples_valid,
            cached.yes_count,
            cached.p_raw,
            cached.reasons,
            None,
        )
    else:
        valid, yes, p_raw, reasons, failure = _ask(
            build_messages(view, settings.prompt_version), client, settings
        )
        if failure is None and p_raw is not None and cache is not None:
            cache.put(
                CachedAnswer(
                    key=key, samples_valid=valid, yes_count=yes, p_raw=p_raw, reasons=reasons
                )
            )

    p_llm = calibrator.apply(p_raw) if calibrator is not None and p_raw is not None else None
    return GroupOpinion(
        incident_id=group.incident_id,
        technique=group.technique,
        entity=group.entity,
        event_count=len(group.events),
        shown_event_ids=list(view.shown_event_ids),
        status="ok" if failure is None else "failed",
        failure=failure,
        method=settings.method,
        samples_requested=settings.samples,
        samples_valid=valid,
        yes_count=yes,
        p_raw=p_raw,
        p_llm=p_llm,
        calibrator_version=calibrator.version if p_llm is not None else None,
        reasons=reasons,
        prompt_version=settings.prompt_version,
        model_id=client.model_id,
        temperature=settings.temperature,
        cache_key=key,
    )


def estimate_incident(
    incident: Incident,
    events: Mapping[str, Event],
    client: OpinionClient,
    settings: OpinionSettings | None = None,
    calibrator: Calibrator | None = None,
    cache: OpinionCache | None = None,
) -> list[GroupOpinion]:
    """One opinion per evidence group of the incident, in C3's group order (sorted keys)."""
    return [
        estimate(group, client, settings, calibrator, cache)
        for group in incident_groups(incident, events)
    ]
