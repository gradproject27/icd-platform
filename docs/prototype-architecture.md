# ICD prototype: architecture and end-to-end path

| | |
|---|---|
| Owner | C1 (Platform and Integration) |
| Roadmap task | 26 (Week 4): resettable demo and prototype note |
| Status | Draft for team review, 24 Nov 2026 |
| Decisions | C1 F1 to F11 (this note, section 7) |

The current build is the **initial prototype of the full ICD system**: every stage of the specified workflow exists and is connected, on one dataset (UNSW-NB15) and with simulated response actions. Later phases widen it (more datasets, login and roles, the model hosted on HPC) without changing the path below.

## 1. Services

`docker compose up --build --detach --wait` starts four containers (`docker-compose.yml`):

| Service | What runs | Notes |
|---|---|---|
| `db` | PostgreSQL 16 | All state: uploads, events, incidents, jobs, reports, masking maps, response lifecycle and audit (migrations 0001 to 0006) |
| `api` | FastAPI (`backend/app/main.py`) | Applies the migrations, then serves the REST API and the response-window WebSocket |
| `worker` | `python -m app.worker`, same image | Runs the job queue (ingest and analysis jobs) and C5's response-window expiry loop |
| `web` | nginx + the React dashboard (`frontend/`) | Serves the dashboard and proxies `/api` to the api |

There is no message broker: the job queue is a Postgres table read with `SELECT ... FOR UPDATE SKIP LOCKED` (`backend/app/jobs/queue.py`).

## 2. The end-to-end path

| Step | What happens | Owner | Code |
|---|---|---|---|
| 1 | The analyst uploads a log file; `POST /uploads` answers 202 with a job ID at once | C1, C4 | `app/api/routes.py`, `frontend/src/pages/UploadPage.tsx` |
| 2 | The **ingest job** parses every record into an `Event` or a quarantined record with a reason | C1, C2 | `app/jobs/ingest.py`, `app/ingest/unsw_nb15.py` |
| 3 | The same job correlates the events into incidents and scores their risk, then stores them | C3, C1 | `app/correlation/`, `app/incidents/store.py` |
| 4 | When the ingest job finishes, **one analysis job per incident** is queued in the same transaction, highest risk first | C1 | `app/worker/runner.py`, `app/jobs/analysis.py` |
| 5 | The **analysis job** registers the incident with the response engine (status New, then Under Analysis) | C1, C5 | `app/jobs/analysis.py`, `app/response/engine.py` |
| 6 | C2's builder makes the **masked** evidence package (at most 50 events) and stores the masking map | C2 | `app/evidence/builder.py`, `masking.py` |
| 7 | The model backend answers (or the report cache does); the answer is checked (schema, grounding, injection) and the report stored | AI1 | `app/analysis/service.py`, `store.py` |
| 8 | The response engine checks the freeze gate: valid report, High risk, confidence at or above the threshold, a target host | C5 | `app/response/freeze.py` |
| 9 | If it freezes: the host is isolated (simulated), a response window opens and the dashboard counts down over the WebSocket | C5, C4 | `app/response/engine.py`, `frontend/src/hooks/useResponseWindow.ts` |
| 10 | The analyst decides in the window, or the deadline passes and the system selects; the action is simulated and audited | C5, C4 | `app/response/`, `PendingDecisionPage.tsx` |

A report that fails the checks is a result: the incident's analysis is marked failed and it never freezes (OD-09). A model that does not answer is retried by the queue and then fails with a named reason.

## 3. What is real and what is simulated

| Real | Simulated or stand-in |
|---|---|
| Parsing, quarantine, correlation, risk scoring, masking, report checks, freeze gate, countdown, decisions, audit trail | Every response action (isolate, block, disable account): labelled `[SIMULATED]`, it never reaches a real system (C5 tests) |
| The job queue, retries and lost-worker recovery | The model in the default stack: the `stub` backend writes deterministic `[STUB]` reports so the whole path runs without a GPU |
| | Login: a development identity (`ICD_DEV_USER`, `ICD_DEV_ROLE`) until T2-15 |

## 4. Model backends

The worker reads `ICD_ANALYSIS_BACKEND` (`.env.example`):

| Backend | Use | State |
|---|---|---|
| `stub` | Default; CI, demos without a model | Runs in CI |
| `openai_http` | A served model: Ollama on a laptop, or the faculty CSIT cluster's model service through an SSH tunnel (`docs/ai1-runbook.md`) | AI1 runs 8 to 12 used it with the 27B model from the command line |
| `hpc_batch` | Slurm batch jobs on the national HPC over ssh (`app/hpc/batch.py`, `tools/c1/icd_analyze.sbatch`) | **Built and tested against a fake cluster only.** Not run on a real HPC: no access yet |

**Pending:** hosting the project's own pinned model (Qwen3-8B, or Qwen3-4B as fallback) on HPC. Until then the stub or a served model stands in; nothing else in the path changes when the backend changes.

## 5. Running it

```powershell
copy .env.example .env               # once
docker compose up --build --detach --wait
python tools/c1/demo_reset.py        # empty everything, load the demo file, wait for the analysis
```

`demo_reset.py` stops the worker, empties every app table and stored upload (`app/demo/reset.py`, guarded by `ICD_ALLOW_RESET=1`; the schema stays), starts the worker, uploads the demo file and waits until every incident is analysed. It then lists the incidents and the response windows that opened. The default file is the C3 correlation fixture, where one High incident freezes with the stub model. With C2's demo slice: `--file <slice> --dataset-id unsw-nb15`. **Before a live demo use `--no-upload`** and upload during the demo, because the High incident's 60 s response window opens as soon as the analysis finishes.

Incidents stored before the analysis job existed: `docker compose exec worker python -m app.jobs.analysis --backfill`.

To use the national HPC once access exists: copy `tools/c1/icd_analyze.sbatch` to the cluster and fill in its `CHANGE_ME` lines, put a key that logs in without a password where the worker container can read it, and set the `ICD_HPC_*` variables in `.env`.

## 6. Limits of this build

- One dataset parser (UNSW-NB15); others are later work.
- The AI panel reads `GET /incidents/{id}/report`, which C4 is connecting to the stored reports.
- The real-model numbers in the repo come from the faculty cluster runs (AI1, `docs/ai1-runs/08` to `12`), not from the app's own job.

## 7. C1 decisions behind this note (24 Nov 2026, proposed)

F1 one analysis job per incident, queued with the ingest job's completion; F2 all incidents analysed, highest risk first; F3 `ICD_ANALYSIS_BACKEND` with `stub` default; F4 `hpc_batch` built, not run; F5 the analysis job drives the response engine (register, start, record); F6 no answer is retried then failed, a failed check is a result; F7 report API (moved to C4); F8 `POST /incidents/{id}/analysis` replaces the unbuilt `POST /analysis-jobs`; F9 demo reset; F10 this note; F11 scope-change note sent by the team. Full list with alternatives: the C1 decisions file in the project files.
