"""The analysis service (AI1, workflow step 5): one masked evidence package in, one attempt out.

    attempt = analyze_package(evidence, generator, report_id=..., clock=..., cache=...)

1. Refuse a package that is not masked (NFR-S-07): failed attempt, check S1.
2. Cache (step 11): with a cache and without `force`, a valid report stored for the same key
   (masked package + prompt version + model pin) is returned and no model is called.
3. Send prompt v2 and check the answer with `run_analysis` (P1, P2, G0-G5, M1).
4. Schema retry: when the first answer fails ONLY a format check (P1 no JSON, P2 schema,
   M1 contract), the model gets one more turn with the list of format errors. Grounding
   failures (G*) are never retried: an invented ID or a followed injection is a finding about
   the model, not a typing slip, and must not be repaired by telling it what was wrong.
5. A backend error (no answer: network, timeout, server) is a failed attempt, check X1, with no
   retry here; the job queue owns retries of a run that never answered.
6. A failed attempt has no report and no confidence, so it never reaches the freeze gate
   (`incident_fields.apply_result` sets analysis_status failed and confidence null).
Only valid reports are stored in the cache.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.analysis.backends import BackendError, Generator
from app.analysis.cache import CacheEntry, ReportCache, cache_key
from app.analysis.grounding import Problem
from app.analysis.pipeline import AnalysisResult, ReportMeta, run_analysis
from app.analysis.prompt import PROMPT_VERSION, build_messages, repair_messages
from app.contracts import EvidencePackage

# Checks a second answer may fix: the format of the answer, not its content.
RETRY_CHECKS = frozenset({"P1", "P2", "M1"})
MAX_TRIES = 2


def new_report_id() -> str:
    return f"rep-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Try:
    """One model call and what the checks found."""

    number: int
    raw_output: str | None
    problems: tuple[Problem, ...]
    seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def record(self) -> dict:
        """For storage and run records: no raw text, only what happened."""
        return {
            "number": self.number,
            "problems": [f"{p.check} {p.location}: {p.detail}" for p in self.problems],
            "seconds": round(self.seconds, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


@dataclass(frozen=True)
class AnalysisAttempt:
    """The outcome for one package: a valid report (new or cached) or a failed analysis."""

    incident_id: str
    package_id: str
    cache_key: str | None
    prompt_version: str
    model_id: str
    generated_by: str
    result: AnalysisResult
    tries: tuple[Try, ...] = field(default_factory=tuple)
    cache_hit: bool = False

    @property
    def valid(self) -> bool:
        return self.result.valid

    @property
    def retried(self) -> bool:
        return len(self.tries) > 1

    @property
    def raw_output(self) -> str | None:
        """The answer the result was made from (the last try's)."""
        return self.tries[-1].raw_output if self.tries else None

    def problems(self) -> list[str]:
        """Every problem of every try, as text, for the job result and the run record."""
        found = [f"try {t.number}: {p.check} {p.location}: {p.detail}" for t in self.tries
                 for p in t.problems]  # fmt: skip
        if not self.tries:
            found += [f"{p.check} {p.location}: {p.detail}" for p in self.result.problems()]
        return found


def _failed(
    evidence: EvidencePackage,
    generator: Generator,
    prompt_version: str,
    key: str | None,
    problem: Problem,
    tries: tuple[Try, ...] = (),
) -> AnalysisAttempt:
    return AnalysisAttempt(
        incident_id=evidence.incident_id,
        package_id=evidence.package_id,
        cache_key=key,
        prompt_version=prompt_version,
        model_id=generator.model_id,
        generated_by=generator.generated_by,
        result=AnalysisResult(None, None, None, (problem,)),
        tries=tries,
    )


def analyze_package(
    evidence: EvidencePackage,
    generator: Generator,
    *,
    clock: Callable[[], datetime],
    report_id: str | None = None,
    cache: ReportCache | None = None,
    force: bool = False,
    prompt_version: str = PROMPT_VERSION,
    max_tries: int = MAX_TRIES,
) -> AnalysisAttempt:
    """Analyse one package (module docstring). Never raises for a model fault.

    max_tries=1 turns the schema retry off (replaying recorded answers, ablation X2).
    """
    if not evidence.masked:
        return _failed(
            evidence,
            generator,
            prompt_version,
            None,
            Problem("S1", "evidence", "the package is not masked; it is never sent (NFR-S-07)"),
        )
    key = cache_key(evidence, prompt_version, generator.model_id)
    if cache is not None and not force:
        entry = cache.get(key)
        if entry is not None and entry.report.evidence_package_id == evidence.package_id:
            return AnalysisAttempt(
                incident_id=evidence.incident_id,
                package_id=evidence.package_id,
                cache_key=key,
                prompt_version=prompt_version,
                model_id=generator.model_id,
                generated_by=entry.report.generated_by,
                result=AnalysisResult(None, None, entry.report),
                cache_hit=True,
            )

    messages = build_messages(evidence, prompt_version)
    report_id = report_id or new_report_id()
    tries: list[Try] = []
    result: AnalysisResult | None = None
    for number in range(1, max_tries + 1):
        started = time.monotonic()
        try:
            generation = generator.generate(messages, evidence)
        except BackendError as exc:
            problem = Problem("X1", "backend", str(exc))
            tries.append(Try(number, None, (problem,), time.monotonic() - started))
            return _failed(evidence, generator, prompt_version, key, problem, tuple(tries))
        seconds = time.monotonic() - started
        meta = ReportMeta(
            report_id=report_id,
            generated_at=clock(),
            generated_by=generator.generated_by,  # type: ignore[arg-type]
            model_id=generator.model_id,
            prompt_version=prompt_version,
        )
        result = run_analysis(generation.text, evidence, meta)
        problems = result.problems()
        tries.append(
            Try(
                number,
                generation.text,
                problems,
                seconds,
                generation.prompt_tokens,
                generation.completion_tokens,
            )
        )
        retry = problems and {p.check for p in problems} <= RETRY_CHECKS
        if result.valid or not retry or number == max_tries:
            break
        messages = repair_messages(
            messages, generation.text, [f"{p.check} {p.location}: {p.detail}" for p in problems]
        )

    assert result is not None
    attempt = AnalysisAttempt(
        incident_id=evidence.incident_id,
        package_id=evidence.package_id,
        cache_key=key,
        prompt_version=prompt_version,
        model_id=generator.model_id,
        generated_by=generator.generated_by,
        result=result,
        tries=tuple(tries),
    )
    if cache is not None and result.report is not None:
        cache.put(CacheEntry(key, result.report, attempt.raw_output, clock()))
    return attempt
