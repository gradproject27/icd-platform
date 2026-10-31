from datetime import UTC, datetime

import pytest

from app.ingest import normalize as norm


@pytest.mark.parametrize("value", [None, "", " ", "-", " - "])
def test_sentinels_become_none(value):
    assert norm.clean(value) is None


def test_clean_trims():
    assert norm.clean("  FIN ") == "FIN"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1421927400", datetime(2015, 1, 22, 11, 50, tzinfo=UTC)),
        (" 1421927400 ", datetime(2015, 1, 22, 11, 50, tzinfo=UTC)),
        ("1421927400.5", datetime(2015, 1, 22, 11, 50, 0, 500000, tzinfo=UTC)),
    ],
)
def test_epoch_seconds_is_utc(value, expected):
    moment = norm.epoch_seconds(value)
    assert moment == expected and moment.tzinfo is UTC


@pytest.mark.parametrize("value", [None, "", "-", "abc", "2015-01-22", "99", "1e20", "4102444800"])
def test_bad_epoch_seconds_raise(value):
    with pytest.raises(norm.BadValue):
        norm.epoch_seconds(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("192.0.2.1", "192.0.2.1"),
        (" 192.0.2.1 ", "192.0.2.1"),
        ("2001:DB8::1", "2001:db8::1"),
        ("-", None),
        ("", None),
        ("host-a", None),
        ("192.0.2.256", None),
        ("192.0.2.1:80", None),
    ],
)
def test_ip_address(value, expected):
    assert norm.ip_address(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("80", 80),
        ("0", 0),
        ("65535", 65535),
        ("0x000b", 11),
        ("0XC0A8", 49320),
        ("65536", None),
        ("-1", None),
        ("-", None),
        ("http", None),
    ],
)
def test_port(value, expected):
    assert norm.port(value) == expected


def test_protocol_is_lower_case():
    assert norm.protocol(" TCP ") == "tcp"
    assert norm.protocol("-") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("31", 31), ("0.036", 0.036), ("1e3", 1000.0), ("FIN", "FIN"), ("", None), ("-", None)],
)
def test_scalar(value, expected):
    result = norm.scalar(value)
    assert result == expected and type(result) is type(expected)


def test_id_part_keeps_the_id_character_set():
    assert norm.id_part("UNSW-NB15_1") == "UNSW-NB15_1"
    assert norm.id_part("my flows (copy).csv") == "my_flows_copy_.csv"
    assert norm.id_part("../../") == "file"
    assert len(norm.id_part("x" * 500)) == 60


def test_normalizer_is_deterministic():
    values = ["1421927400", "0x000b", "192.0.2.1", " TCP ", "0.036"]
    first = [
        norm.epoch_seconds(values[0]),
        norm.port(values[1]),
        norm.ip_address(values[2]),
        norm.protocol(values[3]),
        norm.scalar(values[4]),
    ]
    second = [
        norm.epoch_seconds(values[0]),
        norm.port(values[1]),
        norm.ip_address(values[2]),
        norm.protocol(values[3]),
        norm.scalar(values[4]),
    ]
    assert first == second
