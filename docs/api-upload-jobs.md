# Upload, job and analysis API (Week 2)

| | |
|---|---|
| Owner | C1 (Platform & Integration) |
| Status | **Built:** `GET /datasets`, `POST /uploads`, `GET /uploads/{id}`, `GET /jobs/{id}`, the events and quarantine pages, and the ingest worker, which ends by storing the upload's incidents ([incident-storage.md](incident-storage.md)) and queuing one **analysis job** per incident (24 Nov, C1 decisions F1 to F8, [prototype-architecture.md](prototype-architecture.md)). Re-run: `POST /incidents/{id}/analysis` ([api-incidents.md](api-incidents.md)). **Dropped:** the Week 2 proposals `POST /analysis-jobs` and `GET /jobs/{id}/report`; the report is read with `GET /incidents/{id}/report`. Demo: `tools/c1/week2_demo.py`, reset: `tools/c1/demo_reset.py` |
| Week 2 plan | Section 4, steps 1 to 5; handoff "C1 to C4: endpoint request/response examples" |
| Shapes (source of truth) | `backend/app/api/schemas.py` |
| JSON Schemas (generated) | `docs/api/schemas/*.schema.json` |
| Examples (one per state) | `docs/api/examples/*.json` |
| Tests | `backend/tests/api/test_api_shapes.py` |

These are API shapes, not shared data contracts. Where a response carries a contract (an `Event`, an `AnalysisReport`), it is the contract from `backend/app/contracts/` unchanged.

## 1. Base URL

The browser calls the same origin with the prefix `/api`, which nginx (Docker) and the Vite dev server strip. So `POST /api/uploads` in the browser reaches `POST /uploads` on the API. The paths below are written without `/api`, as the API sees them. `status_url` in a response is also without `/api`.

There is no login in Week 2 (login is Week 5), so no endpoint needs a session yet.

## 2. Endpoints

| Method and path | What it does | Success | Example |
|---|---|---|---|
| `GET /datasets` | The dataset choices for the upload form, accepted extensions and the size limit | 200 `DatasetList` | [dataset-list.json](api/examples/dataset-list.json) |
| `POST /uploads` | Store a file and queue an ingest job. Returns at once and never waits for processing | **202** `UploadAccepted`, header `Location: /jobs/{job_id}` | [upload-accepted.json](api/examples/upload-accepted.json) |
| `GET /uploads/{upload_id}` | The stored upload: name, size, SHA-256, dataset, its job | 200 `Upload` | [upload.json](api/examples/upload.json) |
| `GET /jobs/{job_id}` | Status of any job (ingest or analysis) | 200 `Job` | `job-*.json` |
| `GET /uploads/{upload_id}/events` | The Events stored from an upload, in `event_id` order. Query: `label_status` (`flagged`, `unflagged`, `unlabelled`), `limit` (1 to 500, default 100), `after` (the last `event_id` of the previous page) | 200 `EventPage` | [event-page.json](api/examples/event-page.json) |
| `GET /uploads/{upload_id}/ecs` | The upload's Events as **Elastic Common Schema 9.5.0** documents, one JSON object per line (`application/x-ndjson`), oldest first, as a download. Flagged events are `event.kind: alert` with `threat.tactic.*` from `tactics.toml`; ICD's own fields (label, event type, provenance) are under `icd.`. An export view: the Event contract is unchanged (P7; field names under Apache-2.0, `THIRD_PARTY_NOTICES.md`) | 200 NDJSON; 404 `not_found` | none (streamed) |
| `GET /uploads/{upload_id}/quarantine` | Records that could not become Events, with the reason. Query: `limit`, `after` (a `seq`) | 200 `QuarantinePage` | [quarantine-page.json](api/examples/quarantine-page.json) |
| `POST /analysis-jobs` | **Dropped (F8).** Analysis jobs are queued by the ingest job, one per stored incident; a re-run is `POST /incidents/{id}/analysis` | | |
| `GET /jobs/{job_id}/report` | **Dropped (F8).** Read the report with `GET /incidents/{id}/report`; the job's `analysis.report_id` names it | | |

## 3. Upload request

`POST /uploads` with `Content-Type: multipart/form-data` and two fields:

| Field | Required | Value |
|---|---|---|
| `file` | yes | The file. Its extension must be one of `.csv .json .jsonl .log .txt` |
| `dataset_id` | yes | One of the `dataset_id` values from `GET /datasets` |

In the browser:

```ts
const form = new FormData();
form.append("dataset_id", "fixture");
form.append("file", fileInput.files[0]);
// fetch has no upload progress. For the percentage, use XMLHttpRequest and xhr.upload.onprogress.
```

Two notes for C4:
- The shared `request()` in `frontend/src/api/client.ts` aborts after 5 seconds. A large upload takes longer, so the upload call needs its own timeout (or none). Do not set `Content-Type` yourself; the browser sets it with the multipart boundary.
- The file name is shown back in `Upload.filename` for display only. The server stores the file under its `upload_id` and never uses the name as a path.

Limits (decision D5): maximum **512 MB** (the API reads `MAX_UPLOAD_MB`; `GET /datasets` returns the live value as `max_upload_bytes`). An empty file is refused. The format allowlist is provisional until C2 confirms it.

### Request errors

Every error body has the same shape ([error-response.schema.json](api/schemas/error-response.schema.json)):

```json
{"error": {"code": "file_too_large", "message": "The file is larger than the 512 MB limit."}}
```

`message` is plain language and safe to show. Show it, and switch on `code` only when the screen needs to behave differently.

| HTTP | `code` | When | Nothing stored? |
|---|---|---|---|
| 400 | `file_empty` | The file has 0 bytes | yes |
| 413 | `file_too_large` | Over the limit. nginx may answer 413 itself with an HTML body; treat any 413 as this code | yes |
| 415 | `format_not_accepted` | Extension not in the allowlist | yes |
| 422 | `dataset_unknown` | `dataset_id` is not in `GET /datasets` | yes |
| 422 | `validation_error` | A field is missing or malformed | yes |
| 422 | `invalid_evidence` | `POST /analysis-jobs` body is not a valid `EvidencePackage` | yes |
| 404 | `not_found` | Unknown `upload_id` or `job_id` | n/a |
| 409 | `duplicate_upload` | The same file (same SHA-256) was already uploaded for the same `dataset_id`, and that upload's ingest job has not failed. The `Location` header is `/uploads/{earlier upload_id}` and the message names it. A failed earlier upload does not count, so a retry works. Two identical uploads at once: exactly one is accepted ([error-duplicate-upload.json](api/examples/error-duplicate-upload.json)) | yes |
| 409 | `report_not_available` | `GET /jobs/{id}/report` on a job that is not done or has no valid report | n/a |

A rejected upload stores nothing and creates no job, which matches the wireframe state "Upload rejected" (`docs/wireframes.md` 4.2).

## 4. Jobs

### States and stages

```
queued ──► running ──► done
              │
              └──────► failed   (always with error.code and error.message)
```

| `state` | Meaning | `stage` | Final? |
|---|---|---|---|
| `queued` | Waiting for the worker | `null` | no |
| `running` | The worker is on it | set | no |
| `done` | Finished | `null` | yes |
| `failed` | Stopped with a reason | `null` | yes |

`stage` is set only while running:

| `stage` | Ingest job | Analysis job |
|---|---|---|
| `validating` | Checks the stored file | Checks the evidence package (masked, valid) |
| `parsing` | C2's parser reads the file | |
| `storing` | Events and quarantined records are written | |
| `correlating` | C3's correlation groups the stored events into incidents, which are stored | |
| `submitting` | | Evidence file sent to the HPC (or local backend) |
| `waiting_hpc` | | HPC job queued or running |
| `collecting` | | Report file fetched and checked |

**A job never stays `running` forever.** The worker sends a heartbeat. If it dies, the job is picked up again (`attempts` goes up). After `max_attempts` (3) it ends `failed` with `worker_lost`. The HPC wait has a timeout too (`hpc_timeout`).

**Polling.** Call `GET /jobs/{job_id}` about once a second while the state is `queued` or `running`, and stop at `done` or `failed`.

### Wireframe stages

`docs/wireframes.md` 4.2 proposes Uploaded, Validating, Parsing, Correlating, Done. In Week 2:

| Wireframe | API |
|---|---|
| Uploaded | `POST /uploads` answered 202 |
| Validating | `state = running`, `stage = validating` (or still `queued`) |
| Parsing | `stage = parsing` or `storing` |
| Correlating | `stage = correlating` (from Week 3: the job is `done` only once its incidents are stored) |
| Done | `state = done` |

### Counts

A running ingest job may show `counts` as progress; a done ingest job always has them; a queued or failed job has none ([job-ingest-done-with-quarantine.json](api/examples/job-ingest-done-with-quarantine.json)):

| Field | Meaning |
|---|---|
| `records_read` | Records read from the file |
| `events_stored` | Records that became Events |
| `flagged`, `unflagged`, `unlabelled` | Events by dataset label (OD-21). `unlabelled` is never guessed |
| `quarantined` | Records that could not become Events (FR-03) |
| `quarantined_by_reason` | `quarantined` grouped by reason code, for the "Done, with rejected records" box |

The shape enforces "no record disappears": `flagged + unflagged + unlabelled = events_stored` and `events_stored + quarantined = records_read`. If the worker's numbers do not add up, the job fails with `counts_mismatch` instead of reporting wrong numbers.

A failed ingest keeps nothing from that upload, so a retry starts clean.

### Job failure codes

| `code` | Job kind | Meaning |
|---|---|---|
| `no_parser` | ingest | No parser for this dataset yet (`parser_available` was false) |
| `parse_failed` | ingest | The parser stopped on the whole file (one bad record is quarantined, not a failure) |
| `counts_mismatch` | ingest | The counts did not add up |
| `storage_failed` | ingest | The stored file is missing or the database write failed |
| `worker_lost` | both | The worker stopped mid-job `max_attempts` times |
| `unmasked_evidence` | analysis | The package has `masked: false`; raw host, user and IP never leave the app host (NFR-S-07) |
| `hpc_unreachable` | analysis | The HPC could not be reached after 3 tries |
| `hpc_timeout` | analysis | The HPC job did not finish in time |
| `hpc_job_failed` | analysis | The HPC job ended with an error |
| `report_missing` | analysis | The HPC job finished but wrote no report file |
| `correlation_failed` | ingest | The correlation could not store the upload's incidents; nothing from the upload is kept |
| `internal_error` | both | Anything else; the server log has details |

### Analysis jobs

An analysis job takes one stored incident (`payload: {incident_id, force}`): C2's builder makes the masked `EvidencePackage`, AI1's service sends it to the model backend named by `ICD_ANALYSIS_BACKEND` (`stub`, `openai_http` or `hpc_batch`) or answers from the report cache, checks the answer and stores the report, and C5's response engine records the result (freeze or not). While it runs, `stage` is `submitting`, then `waiting_hpc` and `collecting` (hpc_batch), then `collecting`. A model that gives no answer at all is tried again up to `max_attempts` times and then fails with the backend's code (`hpc_unreachable`, `hpc_timeout`, `hpc_job_failed`, `report_missing`). **A report that fails the checks is a result, not a job failure**: the job is `done` with `analysis.report_valid = false` and the reasons in `analysis.problems` ([job-analysis-done-invalid-report.json](api/examples/job-analysis-done-invalid-report.json)). This matches OD-09, where "analysis failed" is a status of the incident. `report_id` and `confidence` are set exactly when the report is valid, so C5's freeze rule can read them directly.

## 5. For C2: the parser interface (proposed)

The worker calls C2's code through one function per dataset. Proposed signature, to be agreed with C2:

```python
from collections.abc import Iterator
from pathlib import Path

from app.contracts import Event


class QuarantinedRecord:  # app.api.schemas.QuarantinedRecord, without seq (the worker numbers them)
    record_ref: str
    reason_code: str
    reason: str
    raw_excerpt: str | None


def parse(path: Path, context: IntakeContext) -> Iterator[Event | QuarantinedRecord]:
    """Yield one item per record read, in file order. Never raise for one bad record."""
```

- `IntakeContext` carries `upload_id`, `dataset_id`, `source_file` (the original name) and `ingested_at`, so every Event gets the same `ingested_at` and a correct `provenance`.
- **One item per record read.** The worker counts what it receives, so the intake summary always matches what was stored.
- A generator, so a 500 MB file never sits in memory.
- Parsers are registered by `dataset_id`; `parser_available` in `GET /datasets` comes from that registry.
- C1 ships one parser, for `fixture`: a JSON list of Events, such as `fixtures/correlation/events.json`. It lets the whole path run before C2's parsers land.

## 6. For AI1: the HPC handoff

With `ICD_ANALYSIS_BACKEND=hpc_batch` the analysis job writes the masked evidence package to a file, copies it to the cluster with scp, submits `tools/c1/icd_analyze.sbatch` (which runs `tools/ai1/icd_analyze.py`) with `sbatch`, polls `squeue` every 30 s for up to 120 minutes, and copies the `icd-hpc-output-v1` file back. No one copies files by hand. Code: `backend/app/hpc/batch.py`; tests against a fake cluster: `backend/tests/hpc/test_batch.py`. **It has not been run against a real HPC**: the team has no HPC access yet. The checked report and the raw model output are stored in `analysis_reports` (AI1, migration 0006).

## 7. Regenerating the schemas

After changing `backend/app/api/schemas.py`:

```powershell
cd backend
python -m app.api.export
```

A test fails if a committed schema is out of date. C4 can generate TypeScript types from `docs/api/schemas/` the same way `npm run contracts:gen` does for `contracts/schemas/`.

## 8. Open questions

| # | Question | Proposed default | Who |
|---|---|---|---|
| 1 | Accepted formats and size limit | `.csv .json .jsonl .log .txt`, 512 MB | C2 |
| 2 | Parser signature (section 5) | As written | C2 |
| 3 | Should ingest also run correlation in the same job from Week 3? | **Decided (15 Nov):** yes, a `correlating` stage at the end of the ingest job | C3, C1 |
| 4 | Who may upload (OD-24) | Security Engineer and System Administrator, from Week 5 when login exists | C5 |
| 5 | Duplicate upload guard (same SHA-256), Week 4 | **Decided (16 Nov, C2-D13):** refuse with 409 `duplicate_upload` and point to the earlier upload (`Location` header), not "warn and accept", because accepting would store the events again and create a second set of incidents. Same file for another dataset, or after a failed upload, is accepted. Code: `app/api/duplicates.py` | C2 |
