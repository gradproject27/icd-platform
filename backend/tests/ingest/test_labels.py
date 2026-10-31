import pytest

from app.contracts import LabelStatus
from app.ingest.labels import LabelMap, LabelProblem

MAPPING = {
    "mapping_version": "test",
    "sources": [
        {
            "dataset_id": "demo",
            "values": [
                {"raw_value": "1", "status": "flagged"},
                {"raw_value": "0", "status": "unflagged"},
                {"raw_value": "maybe", "status": None},
            ],
        }
    ],
}


@pytest.fixture
def labels():
    return LabelMap("demo", MAPPING)


@pytest.mark.parametrize("raw", [None, ""])
def test_missing_label_is_unlabelled(labels, raw):
    label = labels.label(raw)
    assert label.status == LabelStatus.UNLABELLED
    assert label.raw_value is None


def test_missing_label_keeps_attack_type(labels):
    assert labels.label(None, "Exploits").attack_type == "Exploits"


def test_mapped_values(labels):
    flagged = labels.label("1", "Exploits")
    assert (flagged.status, flagged.raw_value, flagged.attack_type) == ("flagged", "1", "Exploits")
    assert labels.label("0").status == LabelStatus.UNFLAGGED
    assert labels.label("0").origin == "dataset"


@pytest.mark.parametrize("raw", ["2", " 1", "1 ", "True", "attack"])
def test_unknown_value_is_never_guessed(labels, raw):
    with pytest.raises(LabelProblem) as problem:
        labels.label(raw)
    assert problem.value.code == "unknown_label"


def test_pending_value_is_quarantined(labels):
    with pytest.raises(LabelProblem) as problem:
        labels.label("maybe")
    assert problem.value.code == "pending_label"


def test_unknown_dataset():
    with pytest.raises(KeyError):
        LabelMap("nope", MAPPING)


def test_packaged_mapping_has_the_unsw_values():
    labels = LabelMap("unsw-nb15")
    assert labels.label("1").status == LabelStatus.FLAGGED
    assert labels.label("0").status == LabelStatus.UNFLAGGED


def test_packaged_mapping_keeps_precinct6_pending_rules():
    labels = LabelMap("precinct6")
    assert labels.label("malicious").status == LabelStatus.FLAGGED
    with pytest.raises(LabelProblem):
        labels.label("Malicious")
