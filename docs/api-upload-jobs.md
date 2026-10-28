# Upload, job and analysis API (Week 2)

| | |
|---|---|
| Owner | C1 (Platform & Integration) |
| Status | **Built:** `GET /datasets`, `POST /uploads`, `GET /uploads/{id}`, `GET /jobs/{id}`, the events and quarantine pages, and the ingest worker. **Next C1 PR:** `POST /analysis-jobs`, `GET /jobs/{id}/report` and the HPC handoff |
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
| `GET /uploads/{upload_id}/quarantine` | Records that could not become Events, with the reason. Query: `limit`, `after` (a `seq`) | 200 `QuarantinePage` | [quarantine-page.json](api/examples/quarantine-page.json) |
| `POST /analysis-jobs` | Queue an analysis of one `EvidencePackage` (JSON body). Used by AI1 and the demo in Week 2; the pipeline calls it in Week 3 | **202** `JobAccepted`, header `Location` | [job-accepted.json](api/examples/job-accepted.json) |
| `GET /jobs/{job_id}/report` | The `AnalysisReport` of a done analysis job with a valid report | 200 `AnalysisReport` (contract) | `contracts/examples/analysis-report.example.json` |

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
| Correlating | **Not in Week 2.** Correlation is wired to ingestion in Week 3; until then skip this step or show it as "not yet" |
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
| `internal_error` | both | Anything else; the server log has details |

### Analysis jobs

An analysis job takes one `EvidencePackage`, sends it through the LLM adapter (mock, HPC or local fallback) and collects the report. **A report that fails the checks is a result, not a job failure**: the job is `done` with `analysis.report_valid = false` and the reasons in `analysis.problems` ([job-analysis-done-invalid-report.json](api/examples/job-analysis-done-invalid-report.json)). This matches OD-09, where "analysis failed" is a status of the incident. `report_id` and `confidence` are set exactly when the report is valid, so C5's freeze rule can read them directly.

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

The analysis job writes the evidence package to a file, sends it to the HPC through one transport, waits, and reads the report file back. No one copies files by hand. The transport and its settings are described in the HPC handoff PR; the shapes above do not change with the transport. Raw model output is stored for every attempt.

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
| 3 | Should ingest also run correlation in the same job from Week 3? | A follow-up `correlate` stage in the same job | C3, C1 |
| 4 | Who may upload (OD-24) | Security Engineer and System Administrator, from Week 5 when login exists | C5 |
| 5 | Duplicate upload guard (same SHA-256), Week 4 | Warn and link to the earlier upload | C2 |
