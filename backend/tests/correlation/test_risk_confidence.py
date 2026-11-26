"""risk-v1 step 6a: the model's C in the risk score (design 9A.2, user decisions of 26 Nov)."""

from app.confidence.values import C_MIN, Confidence, clamp
from app.contracts import RiskFlag
from app.correlation.risk import EventConfidences, score_incident
from tests.correlation.test_risk_score import CORRELATION, NOW, RISK, ev, incident_of


def score(events, confidences=None):
    incident = incident_of(events)
    by_id = {e.event_id: e for e in events}
    reference = max(e.timestamp for e in events)
    return score_incident(incident, by_id, reference, NOW, RISK, CORRELATION, confidences)


def test_without_confidences_the_score_is_risk_v0():
    events = [ev(1, attack="Exploits", src_ip="192.0.2.1")]
    v0 = score(events)
    assert v0.config_version == RISK.config_version
    assert not {RiskFlag.CONFIDENCE_FIXED, RiskFlag.NEEDS_REVIEW} & set(v0.flags)


def test_model_c_replaces_the_dataset_value_and_names_its_inputs():
    events = [ev(1, attack="Exploits", src_ip="192.0.2.1")]
    v0 = score(events)
    low = EventConfidences({"t-001": Confidence(0.2, 0.3, 0.1)}, "clf-a+llm-b+stack-c")
    v1 = score(events, low)
    assert v1.likelihood < v0.likelihood and v1.score < v0.score
    assert v1.config_version == f"{RISK.config_version}+clf-a+llm-b+stack-c"
    assert "p_clf 0.30, p_llm 0.10" in v1.top_contributors[0].reason
    assert RiskFlag.CONFIDENCE_FIXED not in v1.flags


def test_missing_model_value_keeps_the_fixed_c_and_flags_it():
    events = [ev(1, attack="Exploits", src_ip="192.0.2.1"),
              ev(2, attack="DoS", src_ip="192.0.2.2")]  # fmt: skip
    partial = EventConfidences({"t-001": Confidence(0.9, 0.9, None, ("llm_pending",))}, "v")
    risk = score(events, partial)
    assert RiskFlag.CONFIDENCE_FIXED in risk.flags and RiskFlag.LLM_PENDING in risk.flags
    reasons = {c.event_id: c.reason for c in risk.top_contributors}
    assert "(dataset value)" in reasons["t-002"] and "no p_llm" in reasons["t-001"]


def test_review_and_unavailable_flags_reach_the_incident():
    events = [ev(1, attack="Exploits", src_ip="192.0.2.1")]
    risk = score(events, EventConfidences(
        {"t-001": Confidence(0.5, 0.5, 0.5, ("needs_review",))}, "v"))  # fmt: skip
    assert RiskFlag.NEEDS_REVIEW in risk.flags
    risk = score(events, EventConfidences(
        {"t-001": Confidence(0.5, 0.5, None, ("llm_unavailable",))}, "v"))  # fmt: skip
    assert RiskFlag.LLM_UNAVAILABLE in risk.flags and RiskFlag.LLM_PENDING not in risk.flags


def test_clamp_keeps_an_uncertain_attack_in_the_score():
    assert clamp(0.0) == C_MIN and clamp(1.7) == 1.0
    events = [ev(1, attack="Exploits", src_ip="192.0.2.1")]
    risk = score(events, EventConfidences({"t-001": Confidence(clamp(0.0), 0.0, 0.0)}, "v"))
    assert risk.likelihood > 0
