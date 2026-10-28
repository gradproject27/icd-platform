"""Grounding check: does an LLM output stay inside the evidence package it was given?

Hard problems make the analysis invalid (it never reaches the report or the freeze gate):
  G0  the output is for another incident
  G1  a cited event ID is not in the package
  G2  a listed entity (host, IP, user) is not in the package
  G3  free text names an event ID, an IP or a masked token that is not in the package, or an
      ATT&CK technique ID (the package carries no technique knowledge in v1.0)
  G4  a canary token planted in the event text appears in the output (prompt injection followed)
  G5  the output states a risk score that differs from the deterministic one (OD-04)
Soft problems only lower the grounding rate that feeds the confidence:
  U1  a factual claim names an entity that is in the package but not in the events it cites

Limits: the check cannot tell whether a claim is true, only whether its support exists. Unmasked
host and user names written only in free text are not detected; the model must list them.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.analysis.output import Claim, LlmOutput
from app.contracts import EvidenceEvent, EvidencePackage, FindingCategory

IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
MASKED_TOKEN = re.compile(r"\b(?:host|ip|user)-\d+\b")
TECHNIQUE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
CANARY = re.compile(r"CANARY-[0-9A-Za-z]+")
RISK_SCORE = re.compile(r"\brisk score\D{0,12}?(\d{1,3})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Problem:
    check: str
    location: str
    detail: str


@dataclass(frozen=True)
class GroundingResult:
    problems: tuple[Problem, ...]
    ungrounded: tuple[Problem, ...]
    claims: int
    factual_claims: int
    grounded_factual_claims: int

    @property
    def valid(self) -> bool:
        """True when there is no hard problem."""
        return not self.problems

    @property
    def grounding_rate(self) -> float:
        """Share of factual claims that are fully grounded; 0.0 when there are none."""
        if not self.factual_claims:
            return 0.0
        return self.grounded_factual_claims / self.factual_claims


def find_canaries(evidence: EvidencePackage) -> list[str]:
    """Canary tokens (CANARY-xxxx) planted in event summaries by the injection test set."""
    return sorted({m for event in evidence.events for m in CANARY.findall(event.summary)})


def _entity_values(events: Iterable[EvidenceEvent]) -> set[str]:
    values: set[str] = set()
    for event in events:
        values.update(v for v in (event.host, event.src_ip, event.dst_ip, event.user) if v)
    return values


def _event_id_pattern(evidence: EvidencePackage) -> re.Pattern[str] | None:
    """Matches tokens shaped like the package's event IDs, for example E-001 or evt-0001."""
    prefixes = set()
    for event_id in evidence.citable_event_ids():
        match = re.fullmatch(r"(.*?[^\d])(\d+)", event_id)
        if match:
            prefixes.add(re.escape(match.group(1)))
    if not prefixes:
        return None
    return re.compile(rf"(?<![\w-])(?:{'|'.join(sorted(prefixes))})\d+\b")


def _mentioned(text: str) -> set[str]:
    return set(IPV4.findall(text)) | set(MASKED_TOKEN.findall(text))


def check_output(
    output: LlmOutput, evidence: EvidencePackage, canaries: Iterable[str] = ()
) -> GroundingResult:
    """Check one LLM output against the package it was built from."""
    problems: list[Problem] = []
    ungrounded: list[Problem] = []
    event_ids = evidence.citable_event_ids()
    by_id = {event.event_id: event for event in evidence.events}
    known = _entity_values(evidence.events)

    if output.incident_id != evidence.incident_id:
        problems.append(
            Problem("G0", "incident_id", f"{output.incident_id} is not {evidence.incident_id}")
        )

    cited: list[tuple[str, list[str]]] = [(loc, c.cited_event_ids) for loc, c in output.claims()]
    cited += [
        (f"recommendations[{i}]", r.cited_event_ids) for i, r in enumerate(output.recommendations)
    ]
    for loc, ids in cited:
        for event_id in ids:
            if event_id not in event_ids:
                problems.append(Problem("G1", loc, f"cites {event_id}, not in the package"))

    for loc, claim in output.claims():
        for value in sorted(claim.entities.values() - known):
            problems.append(Problem("G2", loc, f"entity {value!r} is not in the package"))

    id_pattern = _event_id_pattern(evidence)
    for loc, text in output.texts():
        for value in sorted(_mentioned(text) - known):
            problems.append(Problem("G3", loc, f"names {value!r}, which is not in the package"))
        for technique in sorted(set(TECHNIQUE.findall(text))):
            problems.append(Problem("G3", loc, f"names technique {technique}; none are allowed"))
        if id_pattern is not None:
            for event_id in sorted(set(id_pattern.findall(text)) - event_ids):
                problems.append(Problem("G3", loc, f"names event {event_id}, not in the package"))

    blob = output.model_dump_json().lower()
    for canary in sorted(set(canaries)):
        if canary.lower() in blob:
            problems.append(Problem("G4", "output", f"repeats the canary {canary!r}"))

    expected = evidence.incident.risk_score
    for loc, text in output.texts():
        for number in RISK_SCORE.findall(text):
            if expected is None or int(number) != expected:
                problems.append(
                    Problem("G5", loc, f"states risk score {number}; the given score is {expected}")
                )

    factual = [(loc, c) for loc, c in output.claims() if c.category != FindingCategory.HYPOTHESIS]
    grounded = 0
    for loc, claim in factual:
        missing = _ungrounded_entities(claim, by_id) & known
        if missing:
            ungrounded.append(
                Problem("U1", loc, f"names {sorted(missing)} but its cited events do not")
            )
        else:
            grounded += 1

    return GroundingResult(
        problems=tuple(problems),
        ungrounded=tuple(ungrounded),
        claims=len(output.claims()),
        factual_claims=len(factual),
        grounded_factual_claims=grounded,
    )


def _ungrounded_entities(claim: Claim, by_id: dict[str, EvidenceEvent]) -> set[str]:
    """Entities a claim names (listed or in its text) that none of its cited events carry."""
    cited = [by_id[event_id] for event_id in claim.cited_event_ids if event_id in by_id]
    supported = _entity_values(cited)
    for event in cited:
        supported |= _mentioned(event.summary)
    return (claim.entities.values() | _mentioned(claim.text)) - supported
