import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from app.api.export import SHAPES
from app.api.schemas import (
    AnalysisOutcome,
    DatasetList,
    DatasetSource,
    ErrorResponse,
    EventPage,
    IntakeCounts,
    Job,
    JobAccepted,
    QuarantinePage,
    Upload,
    UploadAccepted,
)
from app.contracts.export import schema_text

REPO = Path(__file__).resolve().parents[3]
API_DIR = REPO / "docs" / "api"
EXAMPLES_DIR = API_DIR / "examples"

# Example file name prefix -> the shape it shows. The longest matching prefix wins.
EXAMPLE_SHAPES: dict[str, type[BaseModel]] = {
    "dataset-list": DatasetList,
    "upload-accepted": UploadAccepted,
    "upload": Upload,
    "job-accepted": JobAccepted,
    "job-": Job,
    "event-page": EventPage,
    "quarantine-page": QuarantinePage,
    "error-": ErrorResponse,
}

EXAMPLES = sorted(path.stem for path in EXAMPLES_DIR.glob("*.json"))


def shape_of(name: str) -> type[BaseModel]:
    prefixes = [prefix for prefix in EXAMPLE_SHAPES if name.startswith(prefix)]
    assert prefixes, f"docs/api/examples/{name}.json matches no shape in EXAMPLE_SHAPES"
    return EXAMPLE_SHAPES[max(prefixes, key=len)]


def example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def job(**changes) -> dict:
    return {**example("job-ingest-done"), **changes}


@pytest.mark.parametrize("name", SHAPES)
def test_committed_schema_is_up_to_date(name):
    path = API_DIR / "schemas" / f"{name}.schema.json"
    committed = path.read_text(encoding="utf-8") if path.exists() else ""
    assert committed == schema_text(SHAPES[name]), (
        f"docs/api/schemas/{path.name} is out of date. Run `python -m app.api.export` "
        "from backend/ and commit the result."
    )


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_is_valid(name):
    shape_of(name).model_validate(example(name))


def test_every_shape_has_an_example():
    shown = {shape_of(name) for name in EXAMPLES}
    assert set(SHAPES.values()) <= shown


def test_job_examples_cover_every_state():
    states = {example(name)["state"] for name in EXAMPLES if shape_of(name) is Job}
    assert states == {"queued", "running", "done", "failed"}


def test_examples_tell_one_story():
    accepted = example("upload-accepted")
    upload = example("upload")
    done = example("job-ingest-done")
    assert accepted["upload_id"] == upload["upload_id"] == done["upload_id"]
    assert accepted["job_id"] == upload["job_id"] == done["job_id"]
    assert accepted["status_url"] == f"/jobs/{accepted['job_id']}"
    page = example("event-page")
    assert page["next_after"] == page["items"][-1]["event_id"]


def test_datasets_match_label_mapping_sources():
    mapping = json.loads((REPO / "contracts" / "label-mapping.json").read_text(encoding="utf-8"))
    sources = {source["dataset_id"] for source in mapping["sources"]}
    assert {d.value for d in DatasetSource} == sources | {"fixture"}
    listed = [item["dataset_id"] for item in example("dataset-list")["items"]]
    assert sorted(listed) == sorted(d.value for d in DatasetSource)


def test_counts_reject_a_lost_record():
    counts = example("job-ingest-done")["counts"]
    with pytest.raises(ValidationError, match="records_read"):
        IntakeCounts.model_validate({**counts, "records_read": counts["records_read"] + 1})
    with pytest.raises(ValidationError, match="events_stored"):
        IntakeCounts.model_validate({**counts, "flagged": counts["flagged"] - 1})
    with pytest.raises(ValidationError, match="quarantined_by_reason"):
        IntakeCounts.model_validate(
            {**counts, "quarantined": 1, "events_stored": 36, "flagged": 17}
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"state": "failed"}, "error is set exactly when failed"),
        ({"state": "running"}, "stage is set exactly while running"),
        ({"stage": "parsing"}, "stage is set exactly while running"),
        ({"finished_at": None}, "finished_at"),
        ({"upload_id": None}, "upload_id"),
        ({"counts": None}, "a done ingest job has counts"),
        ({"error": {"code": "parse_failed", "message": "x"}}, "error is set exactly"),
    ],
)
def test_job_rejects_inconsistent_states(changes, message):
    with pytest.raises(ValidationError, match=message):
        Job.model_validate(job(**changes))


def test_failed_job_keeps_no_counts():
    failed = example("job-ingest-failed")
    with pytest.raises(ValidationError, match="counts are null"):
        Job.model_validate({**failed, "counts": example("job-ingest-done")["counts"]})


def test_analysis_job_rules():
    done = example("job-analysis-done")
    with pytest.raises(ValidationError, match="analysis is set exactly"):
        Job.model_validate({**done, "analysis": None})
    with pytest.raises(ValidationError, match="analysis jobs have no counts"):
        Job.model_validate({**done, "counts": example("job-ingest-done")["counts"]})


def test_analysis_outcome_valid_iff_report():
    outcome = example("job-analysis-done")["analysis"]
    with pytest.raises(ValidationError, match="report_id and confidence"):
        AnalysisOutcome.model_validate({**outcome, "report_id": None})
    with pytest.raises(ValidationError, match="problems must be empty"):
        AnalysisOutcome.model_validate({**outcome, "problems": ["G1: x"]})
    invalid = example("job-analysis-done-invalid-report")["analysis"]
    with pytest.raises(ValidationError, match="problems must be empty"):
        AnalysisOutcome.model_validate({**invalid, "problems": []})
