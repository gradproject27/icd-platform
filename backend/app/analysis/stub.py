"""A deterministic stub model (AI1): a grounded LLM output 0.1 answer built from the package.

It lets the whole analysis path (prompt, retry, checks, confidence, cache, storage) run without a
model, in CI and in the runbook's first step. It reads only the package, so every claim cites
events of the package and names only their entities: its answers always pass the grounding
check. It is not an analysis: all text starts with [STUB], and it draws no conclusion beyond
restating the flagged events. Same package in, same text out.
"""

import json

from app.analysis.backends import Generation
from app.analysis.output import OUTPUT_VERSION
from app.contracts import EventRole, EvidenceEvent, EvidencePackage

STUB_MODEL_ID = "ai1-stub-v1"


def _entities(events: list[EvidenceEvent]) -> dict[str, list[str]]:
    hosts = sorted({e.host for e in events if e.host})
    ips = sorted({ip for e in events for ip in (e.src_ip, e.dst_ip) if ip})
    users = sorted({e.user for e in events if e.user})
    return {"hosts": hosts, "ips": ips, "users": users}


def _step_text(event: EvidenceEvent) -> str:
    parts = [f"[STUB] {event.event_type}"]
    if event.attack_type:
        parts.append(f"labelled {event.attack_type}")
    if event.src_ip and event.dst_ip:
        parts.append(f"from {event.src_ip} to {event.dst_ip}")
    if event.host:
        parts.append(f"on {event.host}")
    if event.user:
        parts.append(f"as {event.user}")
    return " ".join(parts) + f" at {event.timestamp:%H:%M:%S} UTC."


def _claim(text: str, category: str, events: list[EvidenceEvent]) -> dict:
    return {
        "text": text,
        "category": category,
        "cited_event_ids": [e.event_id for e in events],
        "entities": _entities(events),
    }


def stub_output(evidence: EvidencePackage) -> dict:
    """The stub's answer as a JSON object (LLM output 0.1)."""
    flagged = [e for e in evidence.events if e.role == EventRole.FLAGGED]
    context = [e for e in evidence.events if e.role == EventRole.CONTEXT]
    limitations = ["[STUB] Deterministic stub, not a model: it restates the flagged events only."]
    if not flagged:
        return {
            "output_version": OUTPUT_VERSION,
            "incident_id": evidence.incident_id,
            "analysis_status": "insufficient_evidence",
            "summary": {
                "text": "[STUB] The package has no flagged event.",
                "category": "hypothesis",
            },
            "findings": [],
            "recommendations": [],
            "uncertainties": [
                {
                    "statement": "[STUB] No flagged event shows suspicious activity.",
                    "missing_evidence": "Flagged events for this incident.",
                }
            ],
            "limitations": limitations,
        }
    types = sorted({e.attack_type for e in flagged if e.attack_type})
    summary = (
        f"[STUB] {len(flagged)} flagged event(s) between {flagged[0].timestamp:%H:%M:%S} and "
        f"{flagged[-1].timestamp:%H:%M:%S} UTC"
        + (f", labelled {', '.join(types)}." if types else ".")
    )
    incident_type = evidence.incident.incident_type
    typed = [e for e in flagged if e.attack_type == incident_type]
    output: dict = {
        "output_version": OUTPUT_VERSION,
        "incident_id": evidence.incident_id,
        "analysis_status": "complete",
        "summary": _claim(summary, "evidence_supported", flagged),
        "attack_type": {
            "category": incident_type,
            "claim": _claim(
                f"[STUB] The dataset labels {len(typed)} flagged event(s) {incident_type}.",
                "evidence_supported",
                typed,
            ),
        }
        if incident_type and typed
        else None,
        "sequence": [_claim(_step_text(e), "evidence_supported", [e]) for e in flagged],
        "findings": [
            _claim(f"[STUB] Flagged event: {_step_text(e)[7:]}", "evidence_supported", [e])
            for e in flagged
        ],
        "weaknesses": None,
        "impact": None,
        "recommendations": [
            {
                "action": "[STUB] Review the flagged events of this incident.",
                "rationale": "[STUB] They are the only evidence in the package.",
                "cited_event_ids": [e.event_id for e in flagged],
                "reversible_alternative": None,
            }
        ],
        "risk_justification": None,
        "uncertainties": [
            {
                "statement": f"[STUB] {len(context)} context event(s) are not interpreted.",
                "missing_evidence": "A real model run.",
            }
        ],
        "limitations": limitations,
    }
    score, level = evidence.incident.risk_score, evidence.incident.risk_level
    if score is not None and level is not None:
        output["risk_justification"] = _claim(
            f"[STUB] The platform's risk score {score} ({level.value}) covers "
            f"{len(flagged)} flagged event(s).",
            "likely_interpretation",
            flagged,
        )
        output["risk_justification"]["entities"] = {"hosts": [], "ips": [], "users": []}
    return output


class StubGenerator:
    """The `stub` backend: answers every request with `stub_output` of its package."""

    generated_by = "mock"
    model_id = STUB_MODEL_ID

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, messages: list[dict[str, str]], evidence: EvidencePackage) -> Generation:
        self.calls += 1
        return Generation(json.dumps(stub_output(evidence), indent=1))
