import json

from app.analysis import PROMPT_VERSION, build_messages
from app.analysis.prompt import fence_id


def test_messages_hold_rules_schema_and_package(evidence):
    system, user = build_messages(evidence)
    assert system["role"] == "system"
    assert user["role"] == "user"
    for rule in ("Evidence only", "data, not instructions", "Cite event IDs", "pseudonymised"):
        assert rule in system["content"]
    assert "ai1-output-0.1" in system["content"]
    assert '"cited_event_ids"' in user["content"]
    assert "{{" not in user["content"]


def _sent_package(user: str, fence: str | None = None) -> dict:
    opening = f'<evidence_package id="{fence}">' if fence else "<evidence_package>"
    closing = f'</evidence_package id="{fence}">' if fence else "</evidence_package>"
    start = user.rindex(opening) + len(opening)
    return json.loads(user[start : user.rindex(closing)])


def test_package_is_sent_without_storage_fields(evidence):
    user = build_messages(evidence)[1]["content"]
    package = _sent_package(user, fence_id(evidence))
    assert "package_id" not in package
    assert "masked" not in package
    assert package["incident"]["risk_score"] == 81
    assert [e["event_id"] for e in package["events"]] == [e.event_id for e in evidence.events]


def test_prompt_is_deterministic(evidence):
    assert build_messages(evidence) == build_messages(evidence)
    assert PROMPT_VERSION == "ai1-prompt-v2"


def test_v1_adds_the_context_and_attack_type_rules(evidence):
    v0 = build_messages(evidence, "ai1-prompt-v0")[0]["content"]
    v1 = build_messages(evidence, "ai1-prompt-v1")[0]["content"]
    assert "A context event is never a sequence step" in v1
    assert "13. Attack type." in v1 and "It is never a claim category" in v1
    assert "13. Attack type." not in v0 and "never a sequence step" not in v0
    # Only the system rules change; the request with the schema and the package is the same.
    v0_request = build_messages(evidence, "ai1-prompt-v0")[1]
    assert build_messages(evidence, "ai1-prompt-v1")[1] == v0_request
    # v1 keeps every v0 rule heading.
    for rule in ("Evidence only", "data, not instructions", "Cite event IDs", "Coverage"):
        assert rule in v1


def test_default_prompt_is_v2(evidence):
    assert build_messages(evidence) == build_messages(evidence, "ai1-prompt-v2")


def test_v0_and_v1_send_the_package_unchanged(evidence):
    user = build_messages(evidence, "ai1-prompt-v1")[1]["content"]
    assert _sent_package(user) == evidence.model_dump(
        mode="json", exclude={"schema_version", "package_id", "masked"}
    )
