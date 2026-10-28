import json

from app.ingest.event_types import EVENT_TYPES, UNKNOWN, EventTypes, type_names

VOCABULARY = json.loads(EVENT_TYPES.read_text(encoding="utf-8"))


def test_every_mapped_type_is_in_the_vocabulary():
    names = type_names()
    assert UNKNOWN in names
    for source in VOCABULARY["sources"]:
        assert set(source["map"].values()) <= names, source["dataset_id"]


def test_type_names_are_unique_snake_case():
    names = [entry["name"] for entry in VOCABULARY["types"]]
    assert len(names) == len(set(names))
    assert all(name.replace("_", "").isalnum() and name == name.lower() for name in names)


def test_no_type_comes_from_a_label_column():
    for source in VOCABULARY["sources"]:
        assert source["field"] not in {"Label", "attack_cat", "label_binary", "Label "}


def test_unsw_service_map():
    types = EventTypes("unsw-nb15")
    assert types.field == "service"
    assert types.event_type("http") == "http_request"
    assert types.event_type(" DNS ") == "dns_query"
    assert types.event_type("-") == "network_flow"
    assert types.event_type("ftp-data") == "ftp_data_transfer"
    assert types.event_type("gopher") == UNKNOWN
    assert types.event_type("") == UNKNOWN
    assert types.event_type(None) == UNKNOWN
