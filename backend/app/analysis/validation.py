"""Grounding validation over a set of incidents (AI1, workflow step 10C).

For each analysed incident: was the report valid, how many claims it made, how many factual
claims were supported or unsupported by the events they cite, which hard checks failed, and
the confidence that followed. The totals give the numbers the thesis reports: unsupported-claim
rate, grounding rate, invented citations or entities (G1-G3), followed injections (G4), stated
risk (G5), and how often the schema retry was needed and worked.
"""

from collections import Counter
from dataclasses import dataclass

from app.analysis.grounding import check_output, find_canaries
from app.analysis.pipeline import parse_output
from app.analysis.service import AnalysisAttempt
from app.contracts import EvidencePackage

INVENTION_CHECKS = ("G1", "G2", "G3")


@dataclass(frozen=True)
class GroundingRow:
    name: str
    incident_id: str
    valid: bool
    cache_hit: bool
    tries: int
    retry_fixed: bool
    claims: int | None
    factual_claims: int | None
    supported: int | None
    unsupported: int | None
    hypotheses: int | None
    confidence: float | None
    hard_checks: tuple[str, ...]
    unsupported_locations: tuple[str, ...]
    injected: bool

    def record(self) -> dict:
        return {
            "name": self.name,
            "incident_id": self.incident_id,
            "valid": self.valid,
            "cache_hit": self.cache_hit,
            "tries": self.tries,
            "retry_fixed": self.retry_fixed,
            "claims": self.claims,
            "factual_claims": self.factual_claims,
            "supported": self.supported,
            "unsupported": self.unsupported,
            "hypotheses": self.hypotheses,
            "confidence": self.confidence,
            "hard_checks": list(self.hard_checks),
            "unsupported_locations": list(self.unsupported_locations),
            "injected": self.injected,
        }


def grounding_row(name: str, attempt: AnalysisAttempt, evidence: EvidencePackage) -> GroundingRow:
    """One table row. Counts come from the report (R2) or, for an invalid answer that still
    parses, from re-running the grounding check on it, so failed answers are counted too."""
    report = attempt.result.report
    counts = report.grounding if report is not None else None
    unsupported_at: tuple[str, ...] = ()
    grounding = attempt.result.grounding
    if grounding is None and attempt.raw_output:
        try:
            grounding = check_output(
                parse_output(attempt.raw_output), evidence, find_canaries(evidence)
            )
        except ValueError:
            grounding = None
    if grounding is not None:
        unsupported_at = tuple(p.location for p in grounding.ungrounded)
        if counts is None:
            counts = grounding.counts()
    if attempt.tries:  # every try, so a format error the retry fixed is still shown
        checks = sorted({p.check for t in attempt.tries for p in t.problems})
    else:  # a cache hit or a refused package
        checks = sorted({p.check for p in attempt.result.problems()})
    return GroundingRow(
        name=name,
        incident_id=attempt.incident_id,
        valid=attempt.valid,
        cache_hit=attempt.cache_hit,
        tries=len(attempt.tries),
        retry_fixed=attempt.valid and attempt.retried,
        claims=counts.claims if counts else None,
        factual_claims=counts.factual_claims if counts else None,
        supported=counts.grounded_factual_claims if counts else None,
        unsupported=counts.unsupported if counts else None,
        hypotheses=counts.claims - counts.factual_claims if counts else None,
        confidence=report.confidence if report else None,
        hard_checks=tuple(checks),
        unsupported_locations=unsupported_at,
        injected=bool(find_canaries(evidence)),
    )


def _rate(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(part / whole, 4)


def summarize(rows: list[GroundingRow]) -> dict:
    """Totals over the set (step 10C output)."""
    counted = [r for r in rows if r.factual_claims is not None]
    factual = sum(r.factual_claims or 0 for r in counted)
    supported = sum(r.supported or 0 for r in counted)
    unsupported = sum(r.unsupported or 0 for r in counted)
    checks = Counter(c for r in rows for c in r.hard_checks)
    injected = [r for r in rows if r.injected]
    confidences = [r.confidence for r in rows if r.confidence is not None]
    return {
        "incidents": len(rows),
        "valid": sum(r.valid for r in rows),
        "cache_hits": sum(r.cache_hit for r in rows),
        "retried": sum(r.tries > 1 for r in rows),
        "retry_fixed": sum(r.retry_fixed for r in rows),
        "claims": sum(r.claims or 0 for r in counted),
        "factual_claims": factual,
        "supported_claims": supported,
        "unsupported_claims": unsupported,
        "hypotheses": sum(r.hypotheses or 0 for r in counted),
        "grounding_rate": _rate(supported, factual),
        "unsupported_claim_rate": _rate(unsupported, factual),
        "incidents_with_unsupported_claims": sum(1 for r in counted if r.unsupported),
        "incidents_with_invented_items": sum(
            1 for r in rows if any(c in INVENTION_CHECKS for c in r.hard_checks)
        ),
        "injection_incidents": len(injected),
        "injections_followed": sum(1 for r in injected if "G4" in r.hard_checks),
        "stated_risk": sum(1 for r in rows if "G5" in r.hard_checks),
        "hard_checks": dict(sorted(checks.items())),
        "mean_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "freeze_eligible_confidence": sum(1 for c in confidences if c >= 0.75),
    }


def render_markdown(title: str, rows: list[GroundingRow], summary: dict, setup: dict) -> str:
    def cell(value) -> str:
        if value is None:
            return "–"
        if isinstance(value, float):
            return f"{value:.3f}"
        if isinstance(value, (list, tuple)):
            return ", ".join(value) or "–"
        if isinstance(value, dict):
            return ", ".join(f"{k} {v}" for k, v in value.items()) or "–"
        return str(value)

    lines = [f"# {title}", ""]
    lines += [f"- {key}: {cell(value)}" for key, value in setup.items()]
    lines += [
        "",
        "## Totals",
        "",
        "| Measure | Value |",
        "|---|---|",
    ]
    lines += [f"| {key.replace('_', ' ')} | {cell(value)} |" for key, value in summary.items()]
    lines += [
        "",
        "## Per incident",
        "",
        "| Package | Valid | Tries | Claims | Factual | Supported | Unsupported | Hypotheses "
        "| Confidence | Failed checks | Unsupported at |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        valid = ("yes" if r.valid else "no") + (" (cache)" if r.cache_hit else "")
        lines.append(
            f"| {r.name}{' (injection)' if r.injected else ''} | {valid} | {r.tries} "
            f"| {cell(r.claims)} | {cell(r.factual_claims)} | {cell(r.supported)} "
            f"| {cell(r.unsupported)} | {cell(r.hypotheses)} | {cell(r.confidence)} "
            f"| {cell(r.hard_checks)} | {cell(r.unsupported_locations)} |"
        )
    lines.append("")
    return "\n".join(lines)
