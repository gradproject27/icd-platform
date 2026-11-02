"""Evidence package builder (T3-06): event choice, order, cap, counts, determinism."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.analysis.grounding import MASKED_TOKEN
from app.contracts import Event, EventRole, EvidencePackage, Incident
from app.contracts.evidence import MAX_EVIDENCE_EVENTS
from app.correlation import correlate, load_config, score_incidents
from app.evidence import MissingEvents, build_package, find_leaks, select_events
from app.ingest.interface import IntakeContext
from app.ingest.unsw_nb15 import parse_unsw_nb15
from app.llm.adapter import uncited_event_ids
from app.llm.mock import MockAnalyzer

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def ev(n, seconds=0, status="flagged", **fields):
    raw = {"flagged": "1", "unflagged": "0", "unlabelled": None}[status]
    return Event.model_validate(
        {
            "event_id": f"t-{n:03d}",
            "timestamp": (T0 + timedelta(seconds=seconds)).isoformat(),
            "ingested_at": NOW.isoformat(),
            "event_type": "network_flow",
            "label": {"status": status, "raw_value": raw, "attack_type": None},
            "summary": "tcp flow",
            "provenance": {
                "dataset_id": "test",
                "source_file": "test.csv",
                "record_ref": f"test.csv:{n}",
                "source_format": "csv",
            },
            **fields,
        }
    )


def incident(events, incident_id="inc-test"):
    first = min(events, key=lambda e: (e.timestamp, e.event_id))
    return Incident.model_validate(
        {
            "incident_id": incident_id,
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "first_event_at": min(e.timestamp for e in events).isoformat(),
            "last_event_at": max(e.timestamp for e in events).isoformat(),
            "events": [
                {
                    "event_id": e.event_id,
                    "role": "flagged" if e.label.status == "flagged" else "context",
                    "link_keys": [] if e is first else ["ip_pair"],
                    "linked_at": NOW.isoformat(),
                }
                for e in events
            ],
        }
    )


def fixture_packages():
    raw = json.loads((ROOT / "fixtures/correlation/events.json").read_text(encoding="utf-8"))
    events = [Event.model_validate(e) for e in raw]
    config = load_config()
    result = correlate(events, config, NOW)
    incidents = score_incidents(result.incidents, events, NOW, correlation=config)
    return events, [(inc, *build_package(inc, events, NOW)) for inc in incidents]


def test_every_fixture_incident_gives_a_valid_masked_package():
    events, built = fixture_packages()
    assert len(built) == 13
    for inc, package, masked in built:
        EvidencePackage.model_validate(package.model_dump(mode="json"))
        assert package.masked is True
        assert package.incident_id == inc.incident_id
        assert package.total_event_count == len(inc.events)
        assert {e.event_id for e in package.events} <= {link.event_id for link in inc.events}
        assert find_leaks(package.model_dump(mode="json"), masked.masking_map) == []


def test_flagged_first_in_time_order_then_context():
    events = [ev(1, 30), ev(2, 0), ev(3, 10, "unflagged"), ev(4, 5, "unlabelled")]
    chosen = select_events(incident(events), {e.event_id: e for e in events})
    assert [(e.event_id, role) for e, role in chosen] == [
        ("t-002", EventRole.FLAGGED),
        ("t-001", EventRole.FLAGGED),
        ("t-004", EventRole.CONTEXT),
        ("t-003", EventRole.CONTEXT),
    ]


def test_cap_keeps_the_first_50_flagged_and_marks_truncated():
    events = [ev(n, seconds=n) for n in range(1, 61)] + [ev(99, 5, "unflagged")]
    package, _ = build_package(incident(events), events, NOW)
    assert len(package.events) == MAX_EVIDENCE_EVENTS
    assert [e.event_id for e in package.events] == [f"t-{n:03d}" for n in range(1, 51)]
    assert package.truncated is True
    assert package.total_event_count == 61
    assert package.incident.flagged_event_count == 60
    assert package.incident.context_event_count == 1


def test_context_nearest_in_time_fills_the_free_places():
    flagged = [ev(n, seconds=1000 + n) for n in range(1, 46)]  # 45 flagged, 5 free places
    context = [ev(100 + n, seconds=1000 + 45 + 10 * n, status="unflagged") for n in range(1, 9)]
    context.append(ev(200, seconds=0, status="unlabelled"))  # far before
    package, _ = build_package(incident(flagged + context), flagged + context, NOW)
    chosen = [e.event_id for e in package.events if e.role == EventRole.CONTEXT]
    assert chosen == ["t-101", "t-102", "t-103", "t-104", "t-105"]
    assert package.truncated is True


def test_same_input_gives_the_same_package():
    events = [ev(1, 0, src_ip="198.51.100.7"), ev(2, 60, "unflagged", src_ip="198.51.100.7")]
    first, _ = build_package(incident(events), events, NOW)
    again, _ = build_package(incident(list(reversed(events))), list(reversed(events)), NOW)
    assert first.model_dump() == again.model_dump()
    later, _ = build_package(incident(events), events, NOW + timedelta(hours=1))
    assert later.package_id == first.package_id  # created_at is not part of the ID


def test_package_id_changes_with_the_events():
    a = [ev(1, 0)]
    b = [ev(1, 0), ev(2, 1, "unflagged")]
    assert (
        build_package(incident(a), a, NOW)[0].package_id
        != build_package(incident(b), b, NOW)[0].package_id
    )


def test_long_incident_id_still_gives_a_valid_package_id():
    events = [ev(1)]
    package, _ = build_package(incident(events, "i" * 128), events, NOW)
    assert len(package.package_id) <= 128


def test_missing_linked_events_are_refused():
    events = [ev(1), ev(2, 1, "unflagged")]
    with pytest.raises(MissingEvents):
        build_package(incident(events), events[:1], NOW)


def test_role_that_does_not_match_the_label_is_refused():
    events = [ev(1), ev(2, 1, "unflagged")]
    inc = incident(events).model_copy()
    data = inc.model_dump(mode="json")
    data["events"][1]["role"] = "flagged"
    with pytest.raises(ValueError, match="does not match"):
        build_package(Incident.model_validate(data), events, NOW)


def test_host_count_counts_distinct_real_hosts():
    events = [ev(1, host="web-01"), ev(2, 1, host="web-01"), ev(3, 2, "unflagged", host="db-01")]
    package, _ = build_package(incident(events), events, NOW)
    assert package.incident.host_count == 2


def test_unsw_sample_incident_has_no_raw_ip_in_the_prompt_payload():
    context = IntakeContext("upl-test", "unsw-nb15", "UNSW-NB15_1.csv", NOW)
    items = list(parse_unsw_nb15(ROOT / "fixtures/ingest/unsw-nb15-sample.csv", context))
    events = [item for item in items if isinstance(item, Event)]
    package, masked = build_package(incident(events), events, NOW)
    text = json.dumps(package.model_dump(mode="json"))
    assert not any(str(e.src_ip) in text or str(e.dst_ip) in text for e in events if e.src_ip)
    assert set(MASKED_TOKEN.findall(text)) <= set(masked.masking_map.tokens)
    assert any(t.startswith("ip-") for t in masked.masking_map.tokens)


def test_mock_analysis_of_a_built_package_cites_only_package_events():
    _, built = fixture_packages()
    for _, package, _ in built:
        report = MockAnalyzer().analyze(package)
        assert uncited_event_ids(report, package) == []


def test_tokens_have_the_style_ai1_grounding_checks():
    """AI1's G3 check finds masked tokens with grounding.MASKED_TOKEN (host-01, ip-01, user-01)."""
    _, built = fixture_packages()
    tokens = {t for _, _, masked in built for t in masked.masking_map.tokens}
    assert tokens
    assert all(MASKED_TOKEN.fullmatch(t) for t in tokens), tokens


def test_cli_prints_one_line_per_incident_and_no_real_value(capsys):
    from app.evidence.cli import main

    assert main([str(ROOT / "fixtures/correlation/events.json")]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 13
    first = lines[0].split()[0]
    assert main([str(ROOT / "fixtures/correlation/events.json"), "--incident", first]) == 0
    package = EvidencePackage.model_validate_json(capsys.readouterr().out)
    events, built = fixture_packages()
    (masked,) = [m for inc, _, m in built if inc.incident_id == first]
    assert find_leaks(package.model_dump(mode="json"), masked.masking_map) == []
