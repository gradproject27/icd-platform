"""Store the masking map and put real values back into a report (T3-07; C2-D6, C2-D7).

    package = build_and_store_package(engine, incident, events, now)   # before the AI call
    masking_map = load_masking_map(engine, report.evidence_package_id, report.incident_id)
    report = unmask_report(report, masking_map)

The report is stored masked, as the model wrote it, so AI1's grounding checks compare it with
the package it was given. `unmask_report` is for display only: the API calls it when it shows
the report to the analyst; the un-masked copy is never stored or sent to the HPC.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from app.contracts import AnalysisReport, Event, EvidencePackage, Incident
from app.evidence.builder import build_package
from app.evidence.masking import MaskingMap
from app.evidence.models import MaskingMapRow


def save_masking_map(
    engine: Engine, package: EvidencePackage, masking_map: MaskingMap, now: datetime
) -> None:
    """Store the map of one package. Saving the same package again changes nothing."""
    if masking_map.incident_id != package.incident_id:
        raise ValueError("the map belongs to another incident")
    rows = [
        {
            "package_id": package.package_id,
            "token": token,
            "incident_id": package.incident_id,
            "kind": kind.value,
            "value": value,
            "created_at": now,
        }
        for token, (kind, value) in masking_map.tokens.items()
    ]
    if not rows:
        return
    statement = insert(MaskingMapRow).values(rows).on_conflict_do_nothing()
    with engine.begin() as connection:
        connection.execute(statement)


def load_masking_map(engine: Engine, package_id: str, incident_id: str) -> MaskingMap:
    """The stored map of one package. Empty when the package had no host, IP or user."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(MaskingMapRow.token, MaskingMapRow.kind, MaskingMapRow.value).where(
                MaskingMapRow.package_id == package_id,
                MaskingMapRow.incident_id == incident_id,
            )
        ).all()
    return MaskingMap.from_tokens(
        incident_id, {token: (kind, value) for token, kind, value in rows}
    )


def build_and_store_package(
    engine: Engine,
    incident: Incident,
    events: Mapping[str, Event] | Iterable[Event],
    now: datetime,
) -> EvidencePackage:
    """Build the masked package and store its map; only the package goes on to the AI."""
    package, masked = build_package(incident, events, now)
    save_masking_map(engine, package, masked.masking_map, now)
    return package


def _unmask(value: str | None, masking_map: MaskingMap) -> str | None:
    return None if value is None else masking_map.unmask(value)


def unmask_report(report: AnalysisReport, masking_map: MaskingMap) -> AnalysisReport:
    """A copy of the report with real values in its text fields, for the analyst's screen.

    IDs, categories and numbers are left as they are. A token the map does not know (one the
    model invented) stays as it is, so the analyst sees that it is not a real value.
    """
    if masking_map.incident_id != report.incident_id:
        raise ValueError("the map belongs to another incident")
    m = masking_map
    return report.model_copy(
        update={
            "summary": m.unmask(report.summary),
            "attack_type": _unmask(report.attack_type, m),
            "sequence": None
            if report.sequence is None
            else [s.model_copy(update={"description": m.unmask(s.description)})
                  for s in report.sequence],
            "findings": [f.model_copy(update={"statement": m.unmask(f.statement)})
                         for f in report.findings],
            "weaknesses": None
            if report.weaknesses is None
            else [m.unmask(w) for w in report.weaknesses],
            "impact": _unmask(report.impact, m),
            "recommendations": [m.unmask(r) for r in report.recommendations],
            "risk_justification": _unmask(report.risk_justification, m),
            "uncertainty": m.unmask(report.uncertainty),
        }
    )  # fmt: skip
