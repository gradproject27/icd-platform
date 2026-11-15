"""The Incident fields C5's freeze rule reads, set from one analysis attempt (C5 decision D2).

report valid = analysis_status "succeeded" and latest_report_id set; confidence = the computed
confidence, set exactly when the analysis succeeded. A failed attempt sets "failed" and clears the
confidence, so it never freezes; the previous report ID stays for the history only.
"""

from datetime import datetime

from app.analysis.pipeline import AnalysisResult
from app.contracts import AnalysisStatus, Incident


def analysis_fields(result: AnalysisResult) -> dict:
    """analysis_status, confidence and (on success) latest_report_id for one attempt."""
    if result.report is None:
        return {"analysis_status": AnalysisStatus.FAILED, "confidence": None}
    return {
        "analysis_status": AnalysisStatus.SUCCEEDED,
        "confidence": result.report.confidence,
        "latest_report_id": result.report.report_id,
    }


def apply_result(incident: Incident, result: AnalysisResult, now: datetime) -> Incident:
    """A new Incident with this attempt applied and counted. Validated by the contract."""
    data = incident.model_dump()
    data.update(analysis_fields(result))
    data["analysis_attempts"] = incident.analysis_attempts + 1
    data["updated_at"] = max(now, incident.updated_at)
    return Incident.model_validate(data)
