"""Replay backend (AI1 + C2, tracker task 31): the demo shows real-model reports without a model.

    ICD_ANALYSIS_BACKEND=replay   (ICD_REPLAY_FILES optional, default: every file in replay_data/)

The real model's answers are recorded once into a file under `app/analysis/replay_data/` (so it
is inside the image). In the demo the worker answers each incident with its recorded text, and
the answer goes through the normal checks: schema, grounding, confidence, freeze gate. Nothing
on the safety path is skipped.

Why not the report cache: the demo reset empties `analysis_reports` (C1, F9), incident IDs are
scoped to the upload (D4), and the cache key holds the model pin (AI1-W3-D5). So a stored report
never matches after a reset and re-upload. The replay key is the masked package WITHOUT its
upload-scoped fields (`incident_id`, `package_id`, `created_at`), plus the prompt version: the
same events, risk and masking give the same key in every upload.

The answer names its incident (`incident_id`, "copied from the package", grounding check G0),
and incident IDs change with the upload. A recording stores the answer with that ID replaced by
`{{incident_id}}`; replay puts the current incident's ID back. The key already proves the answer
was written for these exact events.

Failures are recorded too (decision AI1-W4-D3): an answer that failed the checks is stored and
fails them again on replay; an incident the model never answered replays as a backend error. A
package with no recording at all is also a backend error. The stub never stands in.

Honesty: a replayed report says so. Its model is `replay:<recorded model>`, shown on the report
page; `generated_by` is the site that really ran the model.

Record, with only the Python venv and the cluster tunnel (no Docker; ICD_ANALYSIS_BACKEND and
ICD_LLM_* as in the runbook, section 2):

    python -m app.analysis.replay record fixture ../fixtures/correlation/events.json \
        --out app/analysis/replay_data/fixture.json
    python -m app.analysis.replay record unsw-nb15 ../da../data/demo/unsw-nb15-demo-slice.csv \
        --out app/analysis/replay_data/unsw-nb15-demo-slice.json

`record` builds each incident's package the way the platform does (C2's parser, C3's correlation
and risk over the whole upload, C2's builder) and sends it through the analysis service with the
same tries as the analysis job. `export` does the same from a running platform's database.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analysis.backends import BackendError, Generation, Generator
from app.analysis.prompt import PROMPT_VERSION
from app.analysis.service import MAX_TRIES, AnalysisAttempt, analyze_package
from app.contracts import Event, EvidencePackage

REPLAY_FORMAT = "icd-replay-v1"
REPLAY_KEY_VERSION = "ai1-replay-key-v1"
REPLAY_DIR = Path(__file__).resolve().parent / "replay_data"
MODEL_PREFIX = "replay:"
# Fields that change with the upload, not with the evidence.
UPLOAD_SCOPED_FIELDS = {"created_at", "package_id", "incident_id"}
INCIDENT_PLACEHOLDER = "{{incident_id}}"
RECORD_SCOPE = "upl-record"


def replay_key(evidence: EvidencePackage, prompt_version: str = PROMPT_VERSION) -> str:
    """SHA-256 of the masked package without its upload-scoped fields, and the prompt version."""
    if not evidence.masked:
        raise ValueError("only masked evidence packages are recorded (NFR-S-07)")
    document = {
        "key_version": REPLAY_KEY_VERSION,
        "evidence_package": evidence.model_dump(mode="json", exclude=UPLOAD_SCOPED_FIELDS),
        "prompt_version": prompt_version,
    }
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ReplayEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="replay_key of the package: SHA-256 of the evidence, not a secret.",
    )
    incident_type: str | None = Field(description="For a person reading the file.")
    risk_score: int | None = Field(description="For a person reading the file.")
    valid: bool = Field(description="Whether the recorded answer passed every check.")
    confidence: float | None = Field(description="The report's confidence when valid.")
    failure: str | None = Field(description="What failed, when not valid (for the record).")
    raw_output: str | None = Field(
        description="The model's final answer, masked tokens only, its incident ID written as "
        "{{incident_id}}. Null when the model gave no answer during recording."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.valid and (self.raw_output is None or self.failure is not None):
            raise ValueError("a valid entry has an answer and no failure")
        if not self.valid and not self.failure:
            raise ValueError("an entry that is not valid says what failed")
        return self


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["icd-replay-v1"] = REPLAY_FORMAT
    model_id: str = Field(min_length=1, description="The model that wrote the answers.")
    generated_by: Literal["hpc", "local"] = Field(description="Where that model ran.")
    prompt_version: str = Field(min_length=1)
    recorded_at: datetime
    source: str = Field(min_length=1, description="Which data file, for the record.")
    entries: list[ReplayEntry] = Field(min_length=1)

    def summary(self) -> str:
        valid = sum(1 for e in self.entries if e.valid)
        return (
            f"{len(self.entries)} incidents: {valid} valid, {len(self.entries) - valid} failed "
            f"({self.model_id}, {self.generated_by}, {self.prompt_version})"
        )


def load_recordings(paths: Iterable[Path]) -> list[Recording]:
    return [Recording.model_validate_json(p.read_text(encoding="utf-8")) for p in paths]


def default_files(directory: Path = REPLAY_DIR) -> list[Path]:
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


class ReplayGenerator:
    """Answers a package with its recorded text. One model per demo, as on the cluster."""

    accepts_messages = False  # one try: a repair turn would get the same recorded text back

    def __init__(self, recordings: list[Recording], prompt_version: str = PROMPT_VERSION) -> None:
        if not recordings:
            raise ValueError("replay needs at least one recording (app/analysis/replay_data/)")
        models = {(r.model_id, r.generated_by) for r in recordings}
        if len(models) != 1:
            raise ValueError(f"recordings come from more than one model: {sorted(models)}")
        stale = sorted({r.prompt_version for r in recordings} - {prompt_version})
        if stale:
            raise ValueError(f"recordings use prompt {stale}, the service sends {prompt_version}")
        ((model_id, site),) = models
        self.model_id = MODEL_PREFIX + model_id
        self.generated_by = site
        self.prompt_version = prompt_version
        self.answers: dict[str, str | None] = {}
        for recording in recordings:
            for entry in recording.entries:
                digest = entry.evidence_sha256
                if digest in self.answers and self.answers[digest] != entry.raw_output:
                    raise ValueError(f"two different answers recorded for key {digest[:12]}")
                self.answers[digest] = entry.raw_output

    def generate(self, messages: list[dict[str, str]], evidence: EvidencePackage) -> Generation:
        key = replay_key(evidence, self.prompt_version)
        if key not in self.answers:
            raise BackendError(
                "no recorded answer for this incident (replay); record it on the cluster first"
            )
        answer = self.answers[key]
        if answer is None:
            raise BackendError("replay: the model gave no answer for this incident when recorded")
        return Generation(answer.replace(INCIDENT_PLACEHOLDER, evidence.incident_id))


def generator_from_env(env: Mapping[str, str]) -> ReplayGenerator:
    files = env.get("ICD_REPLAY_FILES", "").strip()
    paths = [Path(p) for p in files.split(",") if p.strip()] if files else default_files()
    return ReplayGenerator(load_recordings(paths))


def _failure(attempt: AnalysisAttempt) -> str | None:
    if attempt.valid:
        return None
    problems = attempt.result.problems()
    if not problems:
        return "failed"
    shown = "; ".join(f"{p.check} {p.location}" for p in problems[:5])
    return shown + (f"; and {len(problems) - 5} more" if len(problems) > 5 else "")


def entry_for(attempt: AnalysisAttempt, evidence: EvidencePackage, risk: int | None) -> ReplayEntry:
    raw = attempt.raw_output
    report = attempt.result.report
    return ReplayEntry(
        evidence_sha256=replay_key(evidence, attempt.prompt_version),
        incident_type=evidence.incident.incident_type,
        risk_score=risk,
        valid=attempt.valid,
        confidence=report.confidence if report is not None else None,
        failure=_failure(attempt),
        raw_output=raw.replace(evidence.incident_id, INCIDENT_PLACEHOLDER) if raw else None,
    )


def platform_packages(
    dataset: str, path: Path, now: datetime, scope: str = RECORD_SCOPE
) -> list[EvidencePackage]:
    """The masked packages the platform builds for one upload of this file, in its order.

    Same steps as the worker: C2's parser (quarantined lines and repeated event IDs left out, the
    first one kept), C3's correlation scoped to the upload, risk over the whole upload with the
    clock W = its latest event time (incidents/store.py), C2's builder.
    """
    from app.api.schemas import DatasetSource
    from app.correlation import correlate, load_config, score_incidents
    from app.evidence.builder import build_package
    from app.ingest.interface import IntakeContext
    from app.ingest.registry import PARSERS

    source = DatasetSource(dataset)
    context = IntakeContext(
        upload_id=scope, dataset_id=source.value, source_file=path.name, ingested_at=now
    )
    events: dict[str, Event] = {}
    for item in PARSERS[source](path, context):
        if isinstance(item, Event) and item.event_id not in events:
            events[item.event_id] = item
    if not events:
        raise ValueError(f"{path.name}: no events parsed")
    config = load_config()
    result = correlate(list(events.values()), config, now, scope=scope)
    reference = max(e.timestamp for e in events.values())
    incidents = score_incidents(
        result.incidents, events.values(), now, None, config, reference=reference
    )
    return [build_package(incident, events, now)[0] for incident in incidents]


def record_file(
    dataset: str,
    path: Path,
    generator: Generator,
    clock: Callable[[], datetime],
    progress: Callable[[str], None] = lambda line: None,
) -> Recording:
    """Ask the model about every incident of one file and record every answer, failures too."""
    if generator.generated_by not in ("hpc", "local"):
        raise ValueError("record a real model (openai_http), not the stub")
    if str(generator.model_id).startswith(MODEL_PREFIX):
        raise ValueError("cannot record from a replay")
    tries = MAX_TRIES if getattr(generator, "accepts_messages", True) else 1
    packages = platform_packages(dataset, path, clock())
    entries = []
    for number, evidence in enumerate(packages, 1):
        started = time.perf_counter()
        attempt = analyze_package(evidence, generator, clock=clock, max_tries=tries)
        entry = entry_for(attempt, evidence, evidence.incident.risk_score)
        entries.append(entry)
        state = "valid" if entry.valid else f"FAILED ({entry.failure})"
        progress(
            f"  {number}/{len(packages)} {evidence.incident.incident_type or 'unknown'} "
            f"risk {evidence.incident.risk_score}: {state}, {len(attempt.tries)} tries, "
            f"{time.perf_counter() - started:.0f} s"
        )
    return Recording(
        model_id=generator.model_id,
        generated_by=generator.generated_by,  # type: ignore[arg-type]
        prompt_version=PROMPT_VERSION,
        recorded_at=clock(),
        source=f"{dataset}: {path.name}",
        entries=entries,
    )


def export_upload(engine, upload_id: str, source: str) -> Recording:
    """The valid reports of one upload's incidents as a recording (newest report per incident).

    The database keeps the answer only for valid reports, so an incident whose analysis failed
    cannot be exported: record it with `record` instead.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.analysis.models import AnalysisReportRow
    from app.evidence.builder import build_package
    from app.evidence.store import load_incident_events
    from app.incidents.models import IncidentRow

    with Session(engine) as session:
        incident_ids = session.scalars(
            select(IncidentRow.incident_id)
            .where(IncidentRow.upload_id == upload_id)
            .order_by(IncidentRow.first_event_at, IncidentRow.incident_id)
        ).all()
    if not incident_ids:
        raise ValueError(f"upload {upload_id} has no stored incidents")
    entries, setups, missing = [], set(), []
    for incident_id in incident_ids:
        incident, events = load_incident_events(engine, incident_id)
        report_id = incident.latest_report_id
        with Session(engine) as session:
            row = session.get(AnalysisReportRow, report_id) if report_id else None
        if row is None or not row.raw_output:
            missing.append(incident_id)
            continue
        if row.model_id and row.model_id.startswith(MODEL_PREFIX):
            raise ValueError(f"{incident_id}: report is itself a replay; record a real model run")
        if row.generated_by not in ("hpc", "local"):
            raise ValueError(f"{incident_id}: report made by the stub; record a real model run")
        setups.add((row.model_id, row.generated_by, row.prompt_version))
        evidence, _ = build_package(incident, {e.event_id: e for e in events}, datetime.now(UTC))
        entries.append(
            ReplayEntry(
                evidence_sha256=replay_key(evidence, row.prompt_version),
                incident_type=incident.incident_type,
                risk_score=incident.risk.score if incident.risk else None,
                valid=True,
                confidence=row.confidence,
                failure=None,
                raw_output=row.raw_output.replace(incident.incident_id, INCIDENT_PLACEHOLDER),
            )
        )
    if missing:
        raise ValueError(
            f"{len(missing)} of {len(incident_ids)} incidents have no valid report "
            f"(first: {missing[0]}); use `record` for them"
        )
    if len(setups) != 1:
        raise ValueError(f"the reports come from more than one model or prompt: {sorted(setups)}")
    ((model_id, site, prompt_version),) = setups
    return Recording(
        model_id=model_id or "unknown",
        generated_by=site,
        prompt_version=prompt_version,
        recorded_at=datetime.now(UTC),
        source=source,
        entries=entries,
    )


def _write(recording: Recording, out: Path | None) -> None:
    text = recording.model_dump_json(indent=2) + "\n"
    if out is None:
        sys.stdout.write(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.analysis.replay")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("record", help="ask the model about every incident of a file")
    p.add_argument("dataset", help="dataset ID, e.g. fixture or unsw-nb15")
    p.add_argument("file", type=Path)
    p.add_argument("--out", type=Path, help="recording file (default: print it)")
    p = sub.add_parser("export", help="one upload's valid reports from the database")
    p.add_argument("--upload", required=True, help="the upload ID (GET /uploads)")
    p.add_argument("--source", required=True, help="which file was uploaded, for the record")
    p.add_argument("--out", type=Path, help="recording file (default: print it)")
    sub.add_parser("check", help="load the recordings the worker would use")
    args = parser.parse_args(argv)

    try:
        if args.command == "check":
            generator = generator_from_env(os.environ)
            print(
                f"{len(generator.answers)} recorded answers, model {generator.model_id}, "
                f"site {generator.generated_by}, prompt {generator.prompt_version}"
            )
            return 0
        if args.command == "record":
            from app.analysis.backends import generator_from_env as backend_from_env

            recording = record_file(
                args.dataset,
                args.file,
                backend_from_env(),
                lambda: datetime.now(UTC),
                lambda line: print(line, file=sys.stderr, flush=True),
            )
        else:
            from app.db import get_engine

            recording = export_upload(get_engine(), args.upload, args.source)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _write(recording, args.out)
    print(recording.summary(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
