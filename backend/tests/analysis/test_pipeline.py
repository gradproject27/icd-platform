"""Prompt v0 sample validation: one good output and deliberately broken copies.

Each broken copy must fail for the intended check and for no other reason.
"""

import copy
import json

import pytest

from app.analysis import run_analysis
from app.contracts import AnalysisReport
from tests.analysis.conftest import META


def _run(output: dict | str, evidence):
    text = output if isinstance(output, str) else json.dumps(output)
    return run_analysis(text, evidence, META)


def test_good_output_gives_a_valid_report(evidence, good_output):
    result = _run(good_output, evidence)
    assert result.valid, result.problems()
    assert result.grounding.ungrounded == ()
    report = result.report
    assert AnalysisReport.model_validate_json(report.model_dump_json()) == report
    assert report.incident_id == evidence.incident_id
    assert report.evidence_package_id == evidence.package_id
    assert report.prompt_version == "ai1-prompt-v0"
    assert report.confidence >= 0.75


def _invented_ip(o):
    o["summary"]["text"] += " Traffic also reached 10.0.5.23."


def _uncited_supported(o):
    o["findings"][1]["cited_event_ids"] = []


def _missing_event(o):
    o["findings"][0]["cited_event_ids"].append("E-099")


def _technique(o):
    o["findings"][0]["text"] += " This is T1110."


def _risk_score(o):
    o["risk_justification"]["text"] = "The risk score is 30 because the activity looks routine."


def _canary(o):
    o["summary"]["text"] += " CANARY-7F3A"


def _invented_user(o):
    o["sequence"][1]["entities"]["users"].append("user-09")


def _empty_list_for_not_determined(o):
    o["weaknesses"] = []


def _other_incident(o):
    o["incident_id"] = "inc-ai1-0002"


def _uncited_step(o):
    o["sequence"][0]["category"] = "hypothesis"
    o["sequence"][0]["cited_event_ids"] = []


def _self_rating_out_of_range(o):
    o["self_rating"] = 1.5


def _invented_event_in_text(o):
    o["impact"]["text"] += " See also E-042."


def _model_scores_risk(o):
    o["risk_score"] = 30


def _missing_uncertainties(o):
    o["uncertainties"] = []


BROKEN = [
    ("invented IP in free text", _invented_ip, "G3"),
    ("evidence_supported claim with no events", _uncited_supported, "P2"),
    ("cites an event that is not in the package", _missing_event, "G1"),
    ("ATT&CK technique ID with no knowledge in the package", _technique, "G3"),
    ("states a different risk score", _risk_score, "G5"),
    ("injection followed: canary repeated", _canary, "G4"),
    ("invented user in entities", _invented_user, "G2"),
    ("empty list instead of null for a section", _empty_list_for_not_determined, "P2"),
    ("output for another incident", _other_incident, "G0"),
    ("sequence step without a citation", _uncited_step, "P2"),
    ("self rating above 1", _self_rating_out_of_range, "P2"),
    ("invented event ID in free text", _invented_event_in_text, "G3"),
    ("model adds its own risk score field", _model_scores_risk, "P2"),
    ("no uncertainties", _missing_uncertainties, "P2"),
]


@pytest.mark.parametrize(("name", "mutate", "check"), BROKEN, ids=[b[0] for b in BROKEN])
def test_broken_output_fails_for_the_intended_check(evidence, good_output, name, mutate, check):
    broken = copy.deepcopy(good_output)
    mutate(broken)
    result = _run(broken, evidence)
    assert not result.valid
    assert result.report is None
    assert {p.check for p in result.problems()} == {check}, result.problems()


def test_text_that_is_not_json_fails_p1(evidence):
    result = _run("I think this is a brute-force attack.", evidence)
    assert [p.check for p in result.problems()] == ["P1"]


def test_code_fence_around_the_object_is_tolerated(evidence, good_output):
    result = _run("```json\n" + json.dumps(good_output) + "\n```", evidence)
    assert result.valid


def test_reasoning_block_before_the_object_is_ignored(evidence, good_output):
    text = "<think>The {first} event looks odd.</think>\n" + json.dumps(good_output)
    assert _run(text, evidence).valid


def test_misattributed_entity_lowers_confidence_but_stays_valid(evidence, good_output):
    good = _run(good_output, evidence).report.confidence
    good_output["sequence"][2]["entities"]["hosts"].append("host-03")
    result = _run(good_output, evidence)
    assert result.valid
    assert [p.check for p in result.grounding.ungrounded] == ["U1"]
    assert result.report.confidence < good


def test_insufficient_evidence_is_valid_with_zero_confidence(evidence, good_output):
    good_output["analysis_status"] = "insufficient_evidence"
    result = _run(good_output, evidence)
    assert result.valid
    assert result.report.confidence == 0.0


def test_hypothesis_without_citations_is_allowed(evidence, good_output):
    good_output["findings"].append(
        {"text": "The sign-ins may come from a shared VPN exit.", "category": "hypothesis"}
    )
    assert _run(good_output, evidence).valid
