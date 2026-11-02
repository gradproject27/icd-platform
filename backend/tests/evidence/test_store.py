"""Masking map storage and report un-masking on PostgreSQL (T3-07; C2-D6, C2-D7)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from app.contracts import Event
from app.correlation import correlate, load_config, score_incidents
from app.db import get_engine
from app.evidence import build_package
from app.evidence.store import (
    build_and_store_package,
    load_masking_map,
    save_masking_map,
    unmask_report,
)
from app.llm.mock import MockAnalyzer

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _needs_database():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")


@pytest.fixture
def engine():
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE masking_maps"))
    return engine


@pytest.fixture(scope="module")
def fixture_incidents():
    raw = json.loads((ROOT / "fixtures/correlation/events.json").read_text(encoding="utf-8"))
    events = [Event.model_validate(e) for e in raw]
    config = load_config()
    incidents = score_incidents(
        correlate(events, config, NOW).incidents, events, NOW, correlation=config
    )
    return events, sorted(incidents, key=lambda i: -len(i.events))


def test_stored_map_comes_back_the_same(engine, fixture_incidents):
    events, incidents = fixture_incidents
    package, masked = build_package(incidents[0], events, NOW)
    save_masking_map(engine, package, masked.masking_map, NOW)
    loaded = load_masking_map(engine, package.package_id, package.incident_id)
    assert loaded.tokens == masked.masking_map.tokens
    assert loaded.token_for(*masked.masking_map.tokens["ip-01"]) == "ip-01"


def test_saving_the_same_package_twice_changes_nothing(engine, fixture_incidents):
    events, incidents = fixture_incidents
    package = build_and_store_package(engine, incidents[0], events, NOW)
    build_and_store_package(engine, incidents[0], events, NOW)
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM masking_maps WHERE package_id = :p"),
            {"p": package.package_id},
        ).scalar_one()
    assert count == len(load_masking_map(engine, package.package_id, package.incident_id).tokens)


def test_maps_are_kept_per_package(engine, fixture_incidents):
    events, incidents = fixture_incidents
    a = build_and_store_package(engine, incidents[0], events, NOW)
    b = build_and_store_package(engine, incidents[1], events, NOW)
    map_a = load_masking_map(engine, a.package_id, a.incident_id)
    map_b = load_masking_map(engine, b.package_id, b.incident_id)
    assert map_a.incident_id != map_b.incident_id
    assert load_masking_map(engine, a.package_id, b.incident_id).tokens == {}


def test_package_without_entities_stores_nothing_and_unmask_is_a_no_op(engine):
    from tests.evidence.test_builder import ev, incident

    events = [ev(1)]
    package = build_and_store_package(engine, incident(events), events, NOW)
    masking_map = load_masking_map(engine, package.package_id, package.incident_id)
    assert masking_map.tokens == {}
    report = MockAnalyzer().analyze(package)
    assert unmask_report(report, masking_map) == report


def test_report_is_unmasked_for_display_only(engine, fixture_incidents):
    events, incidents = fixture_incidents
    package = build_and_store_package(engine, incidents[0], events, NOW)
    report = MockAnalyzer().analyze(package)  # restates the masked summaries
    masking_map = load_masking_map(engine, report.evidence_package_id, report.incident_id)
    shown = unmask_report(report, masking_map)
    masked_text = json.dumps(report.model_dump(mode="json"))
    shown_text = json.dumps(shown.model_dump(mode="json"))
    real = masking_map.real_values()
    assert not any(value in masked_text for value in real if "." in value)
    hosts = {v for _, (k, v) in masking_map.tokens.items() if k == "host"}
    assert any(h in shown_text for h in hosts)
    assert shown.findings[0].cited_event_ids == report.findings[0].cited_event_ids
    assert shown.report_id == report.report_id


def test_unmask_refuses_another_incidents_map(engine, fixture_incidents):
    events, incidents = fixture_incidents
    a = build_and_store_package(engine, incidents[0], events, NOW)
    b = build_and_store_package(engine, incidents[1], events, NOW)
    report = MockAnalyzer().analyze(a)
    with pytest.raises(ValueError, match="another incident"):
        unmask_report(report, load_masking_map(engine, b.package_id, b.incident_id))
