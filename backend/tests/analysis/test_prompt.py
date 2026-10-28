import json

from app.analysis import PROMPT_VERSION, build_messages


def test_messages_hold_rules_schema_and_package(evidence):
    system, user = build_messages(evidence)
    assert system["role"] == "system"
    assert user["role"] == "user"
    for rule in ("Evidence only", "data, not instructions", "Cite event IDs", "pseudonymised"):
        assert rule in system["content"]
    assert "ai1-output-0.1" in system["content"]
    assert '"cited_event_ids"' in user["content"]
    assert "{{" not in user["content"]


def test_package_is_sent_without_storage_fields(evidence):
    user = build_messages(evidence)[1]["content"]
    start = user.index("<evidence_package>") + len("<evidence_package>")
    package = json.loads(user[start : user.index("</evidence_package>")])
    assert "package_id" not in package
    assert "masked" not in package
    assert package["incident"]["risk_score"] == 81
    assert [e["event_id"] for e in package["events"]] == [e.event_id for e in evidence.events]


def test_prompt_is_deterministic(evidence):
    assert build_messages(evidence) == build_messages(evidence)
    assert PROMPT_VERSION == "ai1-prompt-v0"
