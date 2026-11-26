"""Step 7 validation report: reads only the run's report files, never rows."""

import json
from pathlib import Path

from app.confidence import validate as V


def _m(auc, ece, brier=0.02):
    return {"rows": 100, "attacks": 50, "auc": auc, "brier": brier, "ece": ece}


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _run(tmp_path: Path, auc=0.99, ece=0.01, coverage=0.95, stack=True) -> Path:
    run = tmp_path / "run1"
    datasets = ("nf-unsw-nb15-v3", "nf-cse-cic-ids2018-v3")
    _write(
        run / "clf/both/report.json",
        {"per_dataset": {d: {"role": "in-dataset", "calibrated": _m(auc, ece)} for d in datasets}},
    )
    _write(
        run / "clf/unsw-only/report.json",
        {
            "per_dataset": {
                "nf-unsw-nb15-v3": {"role": "in-dataset", "calibrated": _m(0.99, 0.01)},
                "nf-cse-cic-ids2018-v3": {"role": "cross-dataset", "calibrated": _m(0.6, 0.3)},
            }
        },
    )
    _write(
        run / "llm/llm_report.json",
        {"test": {"pooled": {"calibrated": _m(0.8, 0.07)}}, "skipped": {"test": {"no_opinion": 2}}},
    )
    if stack:
        _write(
            run / "stack/stack_report.json",
            {
                "test": {
                    "pooled": {
                        "clamped": _m(auc, ece),
                        "conformal_coverage": coverage,
                        "needs_review_share": 0.04,
                    }
                }
            },
        )
    return run


def test_all_marks_met_is_pass(tmp_path):
    result = V.build(_run(tmp_path))
    assert result["overall"] == "pass"
    assert result["counts"] == {"pass": 7, "fail": 0, "missing": 0}
    measures = {m["measure"] for m in result["measures"]}
    assert "cross-dataset run cic-only" in measures  # absent run reported, not dropped
    assert any("tested nf-cse-cic-ids2018-v3 (cross-dataset)" in m for m in measures)


def test_one_mark_missed_is_fail(tmp_path):
    result = V.build(_run(tmp_path, ece=0.08))
    assert result["overall"] == "fail"
    failed = {c["check"] for c in result["checks"] if c["status"] == "fail"}
    assert failed == {"p_clf ECE, nf-unsw-nb15-v3", "p_clf ECE, nf-cse-cic-ids2018-v3",
                      "C ECE, pooled"}  # fmt: skip


def test_coverage_outside_tolerance_fails(tmp_path):
    result = V.build(_run(tmp_path, coverage=0.90))
    cov = next(c for c in result["checks"] if c["check"] == "conformal coverage, pooled")
    assert cov["status"] == "fail" and result["overall"] == "fail"


def test_missing_report_or_measure_is_incomplete(tmp_path):
    result = V.build(_run(tmp_path, stack=False))
    assert result["overall"] == "incomplete"
    missing = {"check": "stacked C report", "value": None, "mark": "present",
               "status": "missing", "source": "stack/stack_report.json"}  # fmt: skip
    assert missing in result["checks"]
    one_class = V.build(_run(tmp_path / "b", auc=None))
    assert one_class["overall"] == "incomplete"


def test_main_writes_both_files_and_exit_code(tmp_path):
    run = _run(tmp_path)
    assert V.main(["--run", str(run)]) == 0
    md = (run / "validation/validation.md").read_text(encoding="utf-8")
    assert "**Overall: pass**" in md and "(RV1-D7)" in md
    saved = json.loads((run / "validation/validation.json").read_text(encoding="utf-8"))
    assert saved["format"] == "icd-confidence-validation-v1" and saved["run"] == "run1"
    bad = _run(tmp_path / "x", auc=0.9)
    assert V.main(["--run", str(bad), "--out", str(tmp_path / "out")]) == 1
    assert (tmp_path / "out/validation.md").exists()
