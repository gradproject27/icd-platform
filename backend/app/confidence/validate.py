"""The risk-v1 confidence validation report (step 7), from the outputs of one pipeline run.

    python -m app.confidence.validate --run <run dir> [--out <run dir>/validation]

Reads only the shareable outputs (counts and measures, never rows):

    <run>/clf/both/report.json, clf/unsw-only/report.json, clf/cic-only/report.json  (step 4)
    <run>/llm/llm_report.json                                                       (step 5)
    <run>/stack/stack_report.json                                                   (step 6a)

and writes validation.json and validation.md: each check of design 9A.2 with its measured
value, its mark and pass, fail or missing. A missing input, or a measure that cannot be
computed (an AUC on one class only), is reported as missing, never skipped silently. This
covers the confidence C only; the wider validation plan of the risk score (R6) is still open
(RV1-D7).
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PASS_ECE = 0.05
PASS_AUC = 0.95
COVERAGE_TARGET = 0.95
COVERAGE_TOLERANCE = 0.02  # split conformal is valid on average; allow sampling noise


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _check(name: str, value: float | None, mark: str, ok: bool | None,
           source: str) -> dict[str, Any]:  # fmt: skip
    status = "missing" if value is None else ("pass" if ok else "fail")
    return {"check": name, "value": value, "mark": mark, "status": status, "source": source}


def checks(run: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(checks with a pass mark, measures reported without one)."""
    out, info = [], []
    both = _read(run / "clf" / "both" / "report.json")
    src = "clf/both/report.json"
    if both is None:
        out.append(_check("classifier report", None, "present", None, src))
    else:
        for name, entry in sorted(both.get("per_dataset", {}).items()):
            if entry.get("role") != "in-dataset":
                continue
            cal = entry["calibrated"]
            out.append(_check(f"p_clf AUC, {name}", cal["auc"], f">= {PASS_AUC}",
                              cal["auc"] is not None and cal["auc"] >= PASS_AUC, src))  # fmt: skip
            out.append(_check(f"p_clf ECE, {name}", cal["ece"], f"<= {PASS_ECE}",
                              cal["ece"] is not None and cal["ece"] <= PASS_ECE, src))  # fmt: skip
            info.append({"measure": f"p_clf Brier, {name}", "value": cal["brier"], "source": src})
    for single in ("unsw-only", "cic-only"):
        report = _read(run / "clf" / single / "report.json")
        source = f"clf/{single}/report.json"
        if report is None:
            info.append({"measure": f"cross-dataset run {single}", "value": None,
                         "source": source})  # fmt: skip
            continue
        for name, entry in sorted(report.get("per_dataset", {}).items()):
            cal = entry["calibrated"]
            info.append({"measure": f"p_clf trained {single}, tested {name} ({entry['role']}): "
                                    "AUC / ECE", "value": [cal["auc"], cal["ece"]],
                         "source": source})  # fmt: skip
    llm = _read(run / "llm" / "llm_report.json")
    src = "llm/llm_report.json"
    if llm is None or not llm.get("test"):
        out.append(_check("LLM opinion report", None, "present", None, src))
    else:
        for name, entry in sorted(llm["test"].items()):
            cal = entry["calibrated"]
            value = [cal["auc"], cal["ece"], cal["brier"]]
            info.append({"measure": f"p_llm (groups) AUC / ECE / Brier, {name}", "value": value,
                         "source": src})  # fmt: skip
        skipped = llm.get("skipped", {}).get("test", {})
        info.append({"measure": "test groups left out (no opinion, error, other evidence)",
                     "value": skipped, "source": src})  # fmt: skip
    stack = _read(run / "stack" / "stack_report.json")
    src = "stack/stack_report.json"
    if stack is None:
        out.append(_check("stacked C report", None, "present", None, src))
    else:
        for name, entry in sorted(stack["test"].items()):
            c = entry["clamped"]
            out.append(_check(f"C AUC, {name}", c["auc"], f">= {PASS_AUC}",
                              c["auc"] is not None and c["auc"] >= PASS_AUC, src))  # fmt: skip
            out.append(_check(f"C ECE, {name}", c["ece"], f"<= {PASS_ECE}",
                              c["ece"] is not None and c["ece"] <= PASS_ECE, src))  # fmt: skip
            cov = entry["conformal_coverage"]
            out.append(_check(
                f"conformal coverage, {name}", cov,
                f"{COVERAGE_TARGET} ± {COVERAGE_TOLERANCE}",
                cov is not None and abs(cov - COVERAGE_TARGET) <= COVERAGE_TOLERANCE, src,
            ))  # fmt: skip
            info.append({"measure": f"needs_review share, {name}",
                         "value": entry["needs_review_share"], "source": src})  # fmt: skip
            info.append({"measure": f"C Brier, {name}", "value": c["brier"], "source": src})
    return out, info


def _fmt(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list):
        return " / ".join(_fmt(v) for v in value)
    return str(value)


def render(result: dict[str, Any]) -> str:
    lines = [
        "# risk-v1 confidence validation (step 7)",
        "",
        f"Run: `{result['run']}`. Built {result['created']} by `app.confidence.validate`.",
        "",
        f"**Overall: {result['overall']}** ({result['counts']['pass']} pass, "
        f"{result['counts']['fail']} fail, {result['counts']['missing']} missing).",
        "",
        "## Checks with a pass mark (design 9A.2)",
        "",
        "| Check | Value | Mark | Result | Source |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {c['check']} | {_fmt(c['value'])} | {c['mark']} | {c['status']} | "
              f"`{c['source']}` |" for c in result["checks"]]  # fmt: skip
    lines += ["", "## Reported without a pass mark", "", "| Measure | Value | Source |",
              "|---|---|---|"]  # fmt: skip
    lines += [f"| {m['measure']} | {_fmt(m['value'])} | `{m['source']}` |"
              for m in result["measures"]]  # fmt: skip
    lines += ["", "Scope: the event confidence C only. The validation plan of the whole risk "
              "score (R6) is still open (RV1-D7).", ""]  # fmt: skip
    return "\n".join(lines)


def build(run: Path) -> dict[str, Any]:
    marked, info = checks(run)
    counts = {s: sum(1 for c in marked if c["status"] == s) for s in ("pass", "fail", "missing")}
    overall = "incomplete" if counts["missing"] else ("pass" if not counts["fail"] else "fail")
    return {
        "format": "icd-confidence-validation-v1",
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "run": run.name,
        "overall": overall,
        "counts": counts,
        "checks": marked,
        "measures": info,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    out = args.out or args.run / "validation"
    out.mkdir(parents=True, exist_ok=True)
    result = build(args.run)
    (out / "validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (out / "validation.md").write_text(render(result), encoding="utf-8")
    print(f"overall {result['overall']}: {result['counts']}")
    return 0 if result["overall"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
