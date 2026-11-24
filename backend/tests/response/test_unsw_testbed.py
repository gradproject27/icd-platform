"""UNSW-NB15 incidents can freeze (decision C5-D2, config response-v1).

UNSW-NB15 flow records have no host name, so the target host must come from an internal
destination IP. These tests use fixture incident A's events re-addressed the way UNSW-NB15
addresses them: attackers 175.45.176.0/24, victim servers 149.171.126.0/24, normal clients
59.166.0.0/24 (testbed of the UNSW-NB15 paper).
"""

import ipaddress
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.contracts import ScenarioId
from app.ingest.interface import IntakeContext
from app.ingest.unsw_nb15 import parse_unsw_nb15
from app.response import NoFreezeReason, check_freeze, find_targets, lookup

ATTACKER = "175.45.176.1"
VICTIM = "149.171.126.18"
OTHER_VICTIM = "149.171.126.10"
NORMAL_CLIENT = "59.166.0.3"


@pytest.mark.parametrize(
    ("address", "internal"),
    [
        ("149.171.126.0", True),
        ("149.171.126.255", True),
        ("59.166.0.9", True),
        ("175.45.176.3", False),
        ("149.171.127.1", False),  # just outside the victim /24
        ("10.40.85.1", True),  # RFC 1918 is still internal
    ],
)
def test_unsw_testbed_networks(config, address, internal):
    assert config.is_internal(ipaddress.ip_address(address)) is internal


def _unsw_addressed(incident, events):
    """Incident A's events with no host and UNSW testbed addresses.

    Flagged events: attacker -> VICTIM on 5 events, attacker -> OTHER_VICTIM on the rest, and
    one normal client as a second source. Context events keep their own (documentation) IPs.
    """
    flagged = [link.event_id for link in incident.events if link.role == "flagged"]
    assert len(flagged) >= 6, "fixture incident A must have enough flagged events"
    plan = {eid: (ATTACKER, VICTIM) for eid in flagged[:5]}
    plan |= {eid: (ATTACKER, OTHER_VICTIM) for eid in flagged[5:-1]}
    plan[flagged[-1]] = (NORMAL_CLIENT, OTHER_VICTIM)
    out = []
    for event in events:
        update = {"host": None, "user": None, "privileged_user": None}
        if event.event_id in plan:
            src, dst = plan[event.event_id]
            update |= {"src_ip": ipaddress.ip_address(src), "dst_ip": ipaddress.ip_address(dst)}
        out.append(event.model_copy(update=update))
    return out


def test_unsw_incident_gets_the_victim_as_host_and_the_attacker_as_source(
    incident_a, events, config
):
    targets = find_targets(incident_a, _unsw_addressed(incident_a, events), config)
    assert targets.host == VICTIM
    assert targets.source_ip == ATTACKER  # the normal client is internal, never blocked
    assert targets.account is None


def test_high_confident_unsw_incident_freezes_and_recommends_s2(
    incident_a, events, config, analysed
):
    incident = analysed(incident_a, 0.9)
    targets = find_targets(incident, _unsw_addressed(incident_a, events), config)
    check = check_freeze(incident, targets, window_open=False, config=config)
    assert check.freeze, check.reasons
    result = lookup(
        targets, incident_type=incident.incident_type, confidence=incident.confidence, config=config
    )
    assert result.scenario_id == ScenarioId.S2


def test_without_the_testbed_ranges_the_same_incident_never_freezes(
    incident_a, events, config, analysed
):
    """The bug C3 found on #25: with RFC 1918 only, every UNSW incident is no_target_host."""
    rfc1918_only = replace(
        config,
        internal_networks=tuple(
            n
            for n in config.internal_networks
            if not n.overlaps(ipaddress.ip_network("149.171.126.0/24"))
            and not n.overlaps(ipaddress.ip_network("59.166.0.0/24"))
        ),
    )
    incident = analysed(incident_a, 0.9)
    targets = find_targets(incident, _unsw_addressed(incident_a, events), rfc1918_only)
    check = check_freeze(incident, targets, window_open=False, config=rfc1918_only)
    assert NoFreezeReason.NO_TARGET_HOST in check.reasons


def test_parsed_unsw_line_gives_an_internal_destination(tmp_path, config):
    """Through C2's real parser: a UNSW-NB15 line has host=None and a testbed dst_ip."""
    line = (
        f"{ATTACKER},1043,{VICTIM},80,tcp,FIN,0.036,528,304,31,29,0,0,http,117333.3359,"
        "67555.55469,4,4,0,0,0,0,0,0,0,0,0,0,1421927409,1421927409,0,0,0,0,0,0,0,,0,,0,0,0,0,"
        "0,0,0,Exploits,1\n"
    )
    path = tmp_path / "UNSW-NB15_1.csv"
    path.write_text(line, encoding="utf-8")
    context = IntakeContext(
        upload_id="upl-test",
        dataset_id="unsw-nb15",
        source_file="UNSW-NB15_1.csv",
        ingested_at=datetime(2026, 11, 24, tzinfo=UTC),
    )
    (event,) = list(parse_unsw_nb15(path, context))
    assert event.host is None
    assert config.is_internal(event.dst_ip)
    assert not config.is_internal(event.src_ip)
