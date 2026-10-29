"""Targets (decision D3) and the catalogue lookup (OD-20, FR-44, spec section 9)."""

import ipaddress
from dataclasses import replace
from pathlib import Path

import pytest

from app.contracts import ScenarioId
from app.response import (
    Targets,
    confidence_band,
    find_targets,
    load_response_config,
    lookup,
    missing_needs,
)
from app.response.config import DEFAULT_RESPONSE_CONFIG_PATH


def test_fixture_incident_a_targets(incident_a, events, config):
    # web-01 has 4 flagged events, db-01 3. 203.0.113.10 is the only external source.
    # www-data and svc-db have 3 each; svc-db is privileged, so it wins the tie.
    targets = find_targets(incident_a, events, config)
    assert targets == Targets(host="web-01", source_ip="203.0.113.10", account="svc-db")


def test_documentation_range_is_external_although_python_calls_it_private(config):
    address = ipaddress.ip_address("203.0.113.10")
    assert address.is_private  # why a plain is_private check would be wrong
    assert not config.is_internal(address)
    assert config.is_internal(ipaddress.ip_address("10.10.1.21"))


def test_context_events_never_become_targets(events, config, fixture_incident):
    for incident in [fixture_incident(s) for s in ("fx-002", "fx-021", "fx-025", "fx-038")]:
        targets = find_targets(incident, events, config)
        context_ids = {link.event_id for link in incident.events if link.role == "context"}
        context_hosts = {e.host for e in events if e.event_id in context_ids} - {
            e.host for e in events if e.event_id not in context_ids
        }
        assert targets.host not in context_hosts


def test_no_host_falls_back_to_the_internal_destination(incident_a, events, config):
    hostless = [e.model_copy(update={"host": None}) for e in events]
    targets = find_targets(incident_a, hostless, config)
    assert targets.host == "10.10.1.21"


def test_incident_without_any_entity_has_no_targets(events, config, fixture_incident):
    assert find_targets(fixture_incident("fx-005"), events, config) == Targets(None, None, None)


def test_missing_event_is_an_error(incident_a, events, config):
    with pytest.raises(ValueError, match="events missing"):
        find_targets(incident_a, events[:3], config)


@pytest.mark.parametrize(
    ("targets", "expected"),
    [
        (Targets("web-01", "203.0.113.10", "svc-db"), ScenarioId.S2),
        (Targets("web-01", None, "svc-db"), ScenarioId.S3),
        (Targets("web-01", None, None), ScenarioId.S1),
        (Targets(None, "203.0.113.10", "svc-db"), None),
    ],
)
def test_v0_selection_rule(incident_a, config, targets, expected, analysed):
    incident = analysed(incident_a, 0.9)
    result = lookup(
        targets, incident_type=incident.incident_type, confidence=incident.confidence, config=config
    )
    assert result.scenario_id == expected
    assert result.inputs["incident_type"] == "Backdoors"
    assert result.inputs["confidence_band"] == "high"


def test_s4_is_never_selected_automatically(config):
    assert ScenarioId.S4 not in config.selection_order
    assert not config.scenarios[ScenarioId.S4].automatic


def test_confidence_bands(config):
    assert confidence_band(None, config) == "none"
    assert confidence_band(0.74, config) == "low"
    assert confidence_band(0.75, config) == "high"


def test_missing_needs(config):
    s2, s3 = config.scenarios[ScenarioId.S2], config.scenarios[ScenarioId.S3]
    assert missing_needs(s2, Targets("h", None, "a")) == ["source_ip"]
    assert missing_needs(s3, Targets(None, "1.2.3.4", None)) == ["host", "account"]


def test_config_values(config):
    assert config.confidence_threshold == 0.75
    assert config.window_seconds == 60
    assert config.config_version == "response-v0"


def test_config_refuses_s4_in_the_selection_order(tmp_path: Path):
    text = DEFAULT_RESPONSE_CONFIG_PATH.read_text(encoding="utf-8")
    bad = tmp_path / "response.toml"
    bad.write_text(text.replace('order = ["S2", "S3", "S1"]', 'order = ["S4"]'), encoding="utf-8")
    with pytest.raises(ValueError, match="S4 is not automatic"):
        load_response_config(bad)


def test_config_refuses_a_bad_threshold(config):
    with pytest.raises(ValueError):
        replace(config, confidence_threshold=0)
