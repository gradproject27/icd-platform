import json
from pathlib import Path

import pytest

from app.contracts import LabelStatus

ROOT = Path(__file__).resolve().parents[2]
MAPPING = json.loads((ROOT / "contracts" / "label-mapping.json").read_text(encoding="utf-8"))
REGISTER = (ROOT / "docs" / "dataset-licence-register.md").read_text(encoding="utf-8")
SOURCES = MAPPING["sources"]
MAPPED = {s.value for s in LabelStatus} - {LabelStatus.UNLABELLED.value}


def values(source):
    return source.get("values", [])


def all_values():
    return [(s["dataset_id"], v) for s in SOURCES for v in values(s)]


def test_missing_label_is_unlabelled():
    assert MAPPING["rules"]["missing_label"] == LabelStatus.UNLABELLED.value


@pytest.mark.parametrize(("dataset_id", "value"), all_values())
def test_status_is_mapped_or_pending(dataset_id, value):
    if value["status"] is None:
        assert value.get("decision") == "pending", (dataset_id, value["raw_value"])
    else:
        assert value["status"] in MAPPED, (dataset_id, value["raw_value"])


@pytest.mark.parametrize(("dataset_id", "value"), all_values())
def test_meaning_is_documented_or_status_is_null(dataset_id, value):
    assert isinstance(value["meaning"], str) and value["meaning"].strip(), (dataset_id, value)
    if value["meaning"] == "undocumented":
        assert value["status"] is None, (dataset_id, value["raw_value"])


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s["dataset_id"])
def test_no_duplicate_raw_value(source):
    for key in ("values", "attack_type_values"):
        raw = [v["raw_value"] for v in source.get(key, [])]
        assert len(raw) == len(set(raw)), (source["dataset_id"], key)


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s["dataset_id"])
def test_counts_are_non_negative_integers(source):
    profiled = source["profiling_status"] == "profiled"
    for key in ("values", "attack_type_values"):
        for value in source.get(key, []):
            count = value["count"]
            if count is None:
                assert not profiled, (source["dataset_id"], value["raw_value"])
            else:
                assert type(count) is int and count >= 0, (source["dataset_id"], value["raw_value"])


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s["dataset_id"])
def test_dataset_id_is_in_licence_register(source):
    assert f"`{source['dataset_id']}`" in REGISTER


def test_per_dataset_sources_have_no_per_record_values():
    for source in SOURCES:
        if source["label_scope"] == "per_dataset":
            assert source["label_column"] is None
            assert values(source) == []
