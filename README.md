# ICD platform

ICD (Intelligent Cyber Defense) ingests security logs, normalizes them into events, correlates them into incidents, scores risk deterministically, and asks an LLM to explain each incident with cited evidence for an analyst. **All response actions are simulated, labelled as simulated, and audited. Nothing touches a real host.**

## Project status

Week 1 is done. This is what is on `main`:

| Workstream | Delivered in Week 1 |
|---|---|
| C1 | Dev environment (Docker Compose, CI) and backend skeleton: `/health`, Alembic baseline, LLM adapter with a mock |
| C2 | Dataset profile of the 9 data-plan sources, dataset licence register and label mapping v1 (`docs/dataset-profile.md`, `docs/dataset-licence-register.md`, `contracts/label-mapping.json`) |
| C3 | The six shared contracts v1 (models, JSON Schemas, examples, tests) and the correlation and risk-score design |
| C4 | Dashboard skeleton (routes, layout, typed API client, health status), low-fidelity wireframes of every screen, and the server-driven countdown prototype (`docs/wireframes.md`, `docs/countdown-prototype.md`) |
| C5 | The response workflow specification and the authentication approach and threat model |
| AI1 | Analysis layer for real LLM output: LLM output v0, prompt v0, grounding check, confidence, mapping onto AnalysisReport 1.0 (`backend/app/analysis/`); answers to the T1-09 review questions; HPC probe and model benchmark (`tools/ai1/`); design note (`docs/ai1-analysis-design.md`). Five local model runs on the fallback path (Ollama on a 4 GB laptop GPU), failures included (`docs/ai1-runs/`): `llama3.2:3b` reached 3 of 3 valid analyses with every flagged event covered but stays shallow; Qwen3-4B-Instruct gives the most complete analysis but 1 of 3 valid (it quoted the injection canary); none meets the 30 s target, which needs the HPC GPU. HPC results and the model pin are still to fill |

Week 2 is in progress. C4 so far: the upload page on C1's real upload and job API (#20), the incident list (#22) and the pending decision panel (#23), the last two on a dev-only stub server until C3's and C5's endpoints exist (see [Frontend](#frontend)).

Not built yet:

- dataset parsers (C2); only the `fixture` format (a JSON list of Events) is ingested so far;
- the HPC and local LLM backends of analysis jobs (C1 next PR, AI1);
- the correlation engine and risk-score code (C3, Week 2);
- real LLM backends (AI1); only `mock` exists;
- response windows and the decision endpoints in the backend; the dashboard's countdown and decision panel run against the dev-only stub server (`frontend/dev/`);
- the dashboard's incident detail, AI report and login screens; they are still shells (decision D10);
- authentication and response code (C5); the API has no login and no response endpoints yet.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the WSL 2 backend (Windows), or Docker Engine with the Compose plugin (Linux)
- [Git](https://git-scm.com/)
- Python 3.12, only if you run lint and tests outside Docker
- [Node.js](https://nodejs.org/) 22 or later, only if you run the frontend outside Docker

## Start everything

```powershell
git clone https://github.com/gradproject27/icd-platform.git
cd icd-platform
Copy-Item .env.example .env      # Linux/macOS: cp .env.example .env
docker compose up --build
```

Edit `.env` if you want different local credentials or ports. Never commit `.env`.

| Service | What it is | URL |
|---|---|---|
| `api` | FastAPI backend | http://localhost:8000/health, docs at http://localhost:8000/docs |
| `worker` | background worker: runs upload (ingest) jobs from the Postgres queue | none |
| `db` | PostgreSQL 17 | internal only (`docker compose exec db psql -U icd icd`) |
| `web` | React dashboard (upload works end to end; the incident pages need the dev-only stub, see [Frontend](#frontend)); nginx also proxies `/api` and `/ws` to `api` | http://localhost:8080 |

Startup order is enforced by healthchecks: `db` becomes healthy, then `api` starts and applies the migrations, then `worker` and `web` start once `api` is healthy. `api` and `worker` share the `uploads` volume. Check the state with `docker compose ps`. Every service should show `(healthy)`.

Stop with `Ctrl+C`, then `docker compose down`. Add `--volumes` to wipe the database.

## Lint and tests

```powershell
cd backend
python -m venv .venv             # Windows: use py if python opens the Microsoft Store
.venv\Scripts\Activate.ps1       # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cd ..
ruff check .
ruff format --check .
cd backend
pytest -q
```

Expected result without a database: **386 passed, 29 skipped**. The skipped tests need PostgreSQL (`/health` against a real database, the upload API and the worker); they need `DATABASE_URL` with the migrations applied (`alembic upgrade head`) and run in CI, where the result is **415 passed**.

The tests cover:

- the health check, with the database reachable and unreachable;
- the LLM mock: schema-valid output, citations limited to the input event IDs, deterministic output;
- the AI1 analysis layer: a good sample output becomes a valid report, 14 broken outputs each fail for the intended check, confidence, mapping, prompt v0 and the benchmark harness (stub backend, flagged-event coverage, the request it sends to an OpenAI-compatible server);
- every contract, with valid payloads and with invalid payloads that must be rejected;
- schema drift: the committed JSON Schemas must match the models, and the examples must match the schemas;
- the dataset label mapping (`contracts/label-mapping.json`): every value maps to a valid `EventLabel` status, and every source is in the licence register;
- the API shapes in `docs/api/` (schema drift, one valid example per state, consistency rules);
- the upload API (202 at once, refused files store nothing, file names never used as paths) and the worker (end-to-end ingest, quarantine and counts, every failure reason, a crashed worker's job retried from scratch, `worker_lost` after 3 attempts).

CI (`.github/workflows/ci.yml`) runs five jobs on every pull request and every push to `main`:

| Job | What it does |
|---|---|
| `lint` | `ruff check .` and `ruff format --check .` |
| `test` | `alembic upgrade head` and `pytest` against a PostgreSQL service |
| `frontend` | in `frontend/`: `npm ci`, contract types drift check, ESLint, type check, Vitest, production build |
| `secret-scan` | gitleaks over the full git history |
| `compose-smoke` | starts the stack, waits for every healthcheck, calls `/health`, checks the migration revision, checks that `web` serves the dashboard and proxies `/api/health`, then uploads the correlation fixture through nginx and waits for its job to finish with 37 events |

## Frontend

The dashboard (C4) is a React + Vite + TypeScript app in `frontend/`. It only presents data: risk values, deadlines and decisions always come from the backend.

```powershell
cd frontend
npm ci
npm run dev
```

`npm run dev` needs the API on port 8000, for example `docker compose up db api`. Open http://localhost:5173. The browser only calls its own origin: the Vite dev server proxies `/api` and `/ws` to `http://localhost:8000` (with `/api` removed), and in Docker nginx does the same, so no CORS is needed ([auth-and-threat-model.md, A2.14](docs/auth-and-threat-model.md#a214-same-origin-for-dashboard-and-api)).

Checks (the same ones CI runs):

```powershell
npm run contracts:check
npm run lint
npm run typecheck
npm test
npm run build
```

The TypeScript types of the six contracts in `frontend/src/api/contracts/` are generated from `contracts/schemas/` and never edited by hand. The types of C1's API shapes (upload, job, dataset list, error) in `frontend/src/api/c1/` are generated the same way from `docs/api/schemas/`, and kept apart from the contracts. After C3 or C1 changes a schema, run `npm run contracts:gen` and commit the result; `npm run contracts:check` fails CI if either folder is out of date.

**Upload page (Week 2).** `/upload` runs on C1's real upload and job API ([docs/api-upload-jobs.md](docs/api-upload-jobs.md)): choose a dataset source from `GET /datasets` and a file, follow the upload percentage, then the job's processing steps and intake counts (records read, events stored, labelled, unlabelled, quarantined) until it is done or failed. The job ID is kept in the URL (`/upload?job=<job_id>`), so a refresh keeps following the same job and never uploads again. All network code is in `frontend/src/api/`: `request()` for JSON calls and `uploadFile()` (XMLHttpRequest, for upload progress and without the 5-second timeout) for the file. To try it, run the whole stack with `docker compose up --build` and open http://localhost:8080/upload; only the `fixture` dataset has a parser so far, for example `fixtures/correlation/events.json`.

**Incident list on stub data (Week 2).** `/incidents` lists incidents with time, entities, type, risk, state and analysis status, sorted and filtered in the browser; the filters and the sort stay in the URL (`?level=high&state=awaiting_human_decision&sort=risk`). C3's incident API does not exist yet, so a **dev-only stub server** answers the proposed `GET /incidents` and `GET /incidents/{id}` (shape `IncidentSummary` in `frontend/src/api/proposed.ts`, proposed for C3, not a contract) with 13 example incidents, one per incident in C3's correlation fixtures. Every stub answer carries `X-ICD-Stub: 1`, and the page then shows "STUB DATA: scores and states are examples, not C3 results"; the risk values are hand-written placeholders, not C3's scoring. Run `npm run stub:server` (port 8001; add `-- --api http://localhost:8000` to forward every other path, such as uploads, to the real API) and `npm run dev:stub`, then open http://localhost:5173/incidents. `npm run stub:build` regenerates `frontend/dev/stub-data/incidents.json` from the fixtures and the hand-written `overlay.json`; a test fails if it is out of date. The app never imports the stub data: only the proxy target changes.

**Pending decision (Week 2).** `/incidents/:id/decision` shows the response window's countdown from the server's `deadline_at`, the simulated isolation during a freeze, the recommended catalogue scenario, and the three options of [response-workflow-spec.md, section 8](docs/response-workflow-spec.md#8-the-three-analyst-options) with an optional comment and a confirmation step; then the recorded decision, or the server's refusal (409 window expired, 403 not allowed). A compact header shows the incident's ID, state, type, risk, event times and entities (decision D10). After approve or select, the recorded decision carries a simulated `ResponseAction` (the contract as is); the page follows it once a second from Approved to Simulated, succeeded, and the incident to Resolved. A reject during a freeze shows that the simulated isolation was released. Every response label carries SIMULATED; no real system is changed. The decision endpoints (`GET /incidents/{id}/decision`, `POST /incidents/{id}/decisions`) and the summary's `recommended_scenario_id` are **proposed for C5** in `frontend/src/api/proposed.ts`, not contracts; until C5 builds them, the stub server answers them in memory (`decided_by` is `stub-analyst`, as there is no login yet). Started from the command line, the stub server opens a 60-second window for `inc-stub-01` (`-- --no-window` to skip it, `-- --window-seconds 10` for a shorter one, `-- --execute-ms 3000` for the delay before a simulated action succeeds; `curl.exe -X POST http://localhost:8001/dev/response-windows/inc-stub-01` to open it again). The recommended scenarios are hand-picked placeholders, not C5's catalogue lookup.

**Real API or stub.** Which backend each working page uses (detail, AI report and login are still shells):

| Page | Backend | Run |
|---|---|---|
| `/upload` | C1's real API (`/datasets`, `/uploads`, `/jobs/{id}`) | `npm run dev` with the API on port 8000 |
| `/incidents` | stub (proposed for C3) | `npm run stub:server` and `npm run dev:stub` |
| `/incidents/:id/decision` | stub: incident, response window, decision (proposed for C5) | `npm run stub:server` and `npm run dev:stub` |
| all three together | upload forwarded to the real API, the rest on the stub | `npm run stub:server -- --api http://localhost:8000` and `npm run dev:stub` |

On `npm run dev` without the stub, the list and the decision page show the API's 404 as an error with Retry, since the real API has no incident endpoints yet.

**Countdown prototype (T1-11).** The pending-decision page shows the response window's countdown from the server's `deadline_at`; the browser never runs its own 60-second timer. Until the backend has response windows, a local test server plays its role: `npm run countdown:server` (port 8001, `-- --skew-ms 90000` to skew its clock), `npm run dev:countdown` (the dev server proxied to it), and `npm run countdown:measure` (accuracy table). See [docs/countdown-prototype.md](docs/countdown-prototype.md).

## Health check

`GET /health` runs `SELECT 1` against the database:

| Database | Status | Body |
|---|---|---|
| reachable | 200 | `{"status":"ok","database":"ok"}` |
| unreachable | 503 | `{"status":"degraded","database":"unavailable"}` |

The engine is created on first use, so the app starts even when `DATABASE_URL` is unset.

## Upload a file

`POST /uploads` stores the file, queues a job and answers **202** with a job ID at once; the worker processes it. With the stack running:

```powershell
curl.exe -F dataset_id=fixture -F file=@fixtures/correlation/events.json http://localhost:8080/api/uploads
curl.exe http://localhost:8080/api/jobs/<job_id>
curl.exe "http://localhost:8080/api/uploads/<upload_id>/events?label_status=flagged"
```

The job goes `queued`, `running` (with a `stage`), then `done` with the intake counts (records read, flagged, unflagged, unlabelled, quarantined), or `failed` with a reason code. A job never stays `running`: if the worker dies, the job is retried, and after 3 attempts it fails with `worker_lost`. Every endpoint, state and error code, with examples, is in [docs/api-upload-jobs.md](docs/api-upload-jobs.md).

Only `fixture` has a parser so far; an upload for another dataset is stored and its job fails with `no_parser` until C2's parser is registered in `backend/app/ingest/registry.py`. Files are limited to 512 MB (`MAX_UPLOAD_MB`) and `.csv .json .jsonl .log .txt`.

## Shared contracts

ICD's components exchange six contracts: **Event**, **Incident**, **EvidencePackage**, **AnalysisReport**, **ResponseAction** and **AuditRecord**. C3 owns them. They are version `1.0` (`SCHEMA_VERSION` in `backend/app/contracts/common.py`) and are a **draft until frozen at M1**.

| What | Where | Edited by hand |
|---|---|---|
| Pydantic v2 models (the source of truth) | `backend/app/contracts/` | yes |
| JSON Schemas, one per contract | `contracts/schemas/<name>.schema.json` | **no, generated** |
| One valid synthetic example per contract | `contracts/examples/<name>.example.json` | yes |

Python code imports the models from `app.contracts`. Other languages read the JSON Schemas. Nobody redefines the contracts.

After any model change, regenerate the schemas and commit the changed files:

```powershell
cd backend
python -m app.contracts.export
```

A drift test (`backend/tests/contracts/test_schemas.py`) fails CI if a committed schema differs from what the models generate.

After the freeze, a contract change goes through a PR reviewed by C3, lists the affected contracts, regenerates the schemas, and bumps the version if it is not backward compatible. The full rule is in [contracts/README.md](contracts/README.md), and every field is described in [docs/contracts-v1.md](docs/contracts-v1.md).

## LLM adapter

Everything that needs an incident explanation depends on the `LLMAnalyzer` protocol in `backend/app/llm/adapter.py`, never on a concrete backend. `LLMAnalyzer.analyze(evidence)` takes an `EvidencePackage` and returns an `AnalysisReport`, both from `app.contracts`:

```python
from app.llm.adapter import get_analyzer, uncited_event_ids

report = get_analyzer().analyze(evidence)  # EvidencePackage -> AnalysisReport
assert uncited_event_ids(report, evidence) == []  # every cited event ID must exist in the evidence
```

`uncited_event_ids` checks the citations of every finding and every sequence step.

Real backends will pass the model's text to `run_analysis` in `backend/app/analysis/` (AI1), which parses it, runs the grounding checks, computes the confidence and maps it onto `AnalysisReport`; see [docs/ai1-analysis-design.md](docs/ai1-analysis-design.md).

`get_analyzer()` picks the backend from `LLM_BACKEND`. Only `mock` exists for now; any other value raises `ValueError`. `MockAnalyzer` (`backend/app/llm/mock.py`) is deterministic, with no clock, randomness or network. It cites only event IDs that are in the evidence, marks its text `[MOCK]` and its recommendations `[SIMULATED]`, so the rest of ICD runs with no LLM or HPC.

## Database migrations

The schema is managed by [Alembic](https://alembic.sqlalchemy.org/) in `backend/migrations`. The URL always comes from `DATABASE_URL`; it is never written in `alembic.ini`. The `api` container runs `alembic upgrade head` before it starts uvicorn, so `docker compose up` always brings the schema up to date.

Revision `0001` is still the empty baseline: there are no tables yet. Tables come in Week 2 with the code that stores events and incidents, using the contracts.

Add ORM models as subclasses of `app.db.Base`, then create a revision:

```powershell
docker compose exec api alembic revision --autogenerate -m "add incidents table"   # then review the file
docker compose exec api alembic upgrade head
docker compose exec db psql -U icd -d icd -tAc "SELECT version_num FROM alembic_version"
```

Files written inside the container are not on your disk, so you can also run Alembic from `backend/` with your venv and `$env:DATABASE_URL` pointing at a reachable database.

## Documentation

| File | Owner | Task | What it is |
|---|---|---|---|
| [docs/contracts-v1.md](docs/contracts-v1.md) | C3 | T1-07 | Shared data contracts v1: every field of the six contracts, decisions applied, review questions |
| [docs/correlation-and-risk-design.md](docs/correlation-and-risk-design.md) | C3 | T1-08 | Correlation and risk score design: relatedness keys, time window, grouping, risk formula, evaluation |
| [docs/response-workflow-spec.md](docs/response-workflow-spec.md) | C5 | T1-13 | Response workflow specification: lifecycle states, transitions, freeze, 60-second window, simulated catalogue |
| [docs/auth-and-threat-model.md](docs/auth-and-threat-model.md) | C5 | T1-14 | Authentication approach and MVP threat model: sessions, roles and permissions, threats TM-01 to TM-13 |
| [docs/dataset-profile.md](docs/dataset-profile.md) | C2 | T1-05 | Dataset profile: inventory, field mapping to the Event contract, labels, data quality, ground truth, first development subset |
| [docs/dataset-licence-register.md](docs/dataset-licence-register.md) | C2 | T1-06 | Licence register: licence or terms per source, evidence, redistribution, citation, status; rules for using the data |
| [contracts/label-mapping.json](contracts/label-mapping.json) | C2 | T1-06 | Label mapping v1: every dataset label value mapped to an `EventLabel` status |
| [docs/wireframes.md](docs/wireframes.md) | C4 | T1-12 | Low-fidelity dashboard wireframes: every screen with its loading, empty and error states, the SIMULATED badge rule |
| [docs/countdown-prototype.md](docs/countdown-prototype.md) | C4 | T1-11 | Server-driven countdown prototype: offset maths, test server, accuracy results, what the real backend must provide |
| [docs/ai1-analysis-design.md](docs/ai1-analysis-design.md) | AI1 | T1-09 | AI analysis design: HPC feasibility, batch vs. service, model pinning and licence, run record, LLM output v0 mapping, answers to the T1-09 review questions, valid analysis and confidence, prompt v0, validation |
| [tools/ai1/README.md](tools/ai1/README.md) | AI1 | | HPC probe and model benchmark: how to run them on the HPC and locally with Ollama |
| [docs/ai1-runs/README.md](docs/ai1-runs/README.md) | AI1 | | Model-run records of the five local runs (`llama3.2:3b`, Qwen3-4B-Instruct), failures included, with the raw answers and what each run showed |
| [docs/api-upload-jobs.md](docs/api-upload-jobs.md) | C1 | Week 2 | Upload, job status and analysis API: endpoints, request and response examples for every state, error codes, parser interface for C2 |
| [docs/github-setup.md](docs/github-setup.md) | C1 | | GitHub setup: manual steps to create the repo, add members and protect `main` |
| [docs/scope-change-note.md](docs/scope-change-note.md) | C1 | T1-02 | Scope-change note: roadmap vs. approved specification, for the supervisor (draft, not yet sent) |
| [contracts/README.md](contracts/README.md) | C3 | T1-07 | Where the contract models, schemas and examples live; how to regenerate; change rule |
| [CONTRIBUTING.md](CONTRIBUTING.md) | C1 | | Branch names, pull requests, ownership and rules |

## Open team decisions

These are written down but not yet agreed:

| Decision | Who | Where |
|---|---|---|
| Risk weights v0. The decision record is empty; risk scoring (T2-09) does not start until it is filled in. | Whole team | [correlation-and-risk-design.md, section 10](docs/correlation-and-risk-design.md#10-proposed-v0-weights-and-decision-record) |
| Review of EvidencePackage and AnalysisReport (T1-09): AI1's answers are written, C3 to agree | AI1, C3 | [ai1-analysis-design.md, section 6](docs/ai1-analysis-design.md#6-report-schema-llm-output-v0-mapped-onto-analysisreport-10) |
| Agreement on each contract: Event and EvidencePackage (C2); ResponseAction, AuditRecord and Incident (C5); Incident (C1) | C2, C5, C1 | [contracts-v1.md, section 7](docs/contracts-v1.md#7-agreement-checklist) |
| Response window API for the dashboard: REST and WebSocket paths, one socket per incident or per user, reads after a refresh. The countdown prototype already follows spec section 7 | C1, C5 | [countdown-prototype.md, sections 7 and 8](docs/countdown-prototype.md#8-open-questions-for-c1-and-c5) |
| API shapes the screens need: upload stages, event details, risk factor labels, decision type | C1, C2, C3, C5 | [wireframes.md, section 6](docs/wireframes.md#6-open-questions) |
| C4's proposed shapes: `IncidentSummary` with entities and `recommended_scenario_id` (C3), and the decision call `POST /incidents/{id}/decisions` with `GET /incidents/{id}/decision` (C5) | C3, C5 | [frontend/src/api/proposed.ts](frontend/src/api/proposed.ts), PR #23 |
| Which CSV dataset (UNSW-NB15 or CIC-IDS2017), and Precinct6 used as an agreement check only, not ground truth | Whole team | [dataset-profile.md, section 10](docs/dataset-profile.md#10-open-questions-and-review) |
| Unresolved dataset licences (OTRF, EPSS, CIRCL, NVD) and which NIST resource the data plan means | C2, whole team, supervisor | [dataset-licence-register.md, section 4](docs/dataset-licence-register.md#4-open-licence-questions) |
| Analysis confidence and valid-analysis rules for the freeze: AI1's proposal is written, C5 to agree | AI1, C5 | [ai1-analysis-design.md, section 7](docs/ai1-analysis-design.md#7-valid-analysis-and-confidence-response-spec-section-5) |

Each document also marks its own proposals "(proposed, needs team agreement)", for example transition T16 "no response needed" in the response workflow. They are listed in each document's open questions:

- [contracts-v1.md, section 9](docs/contracts-v1.md#9-open-questions)
- [correlation-and-risk-design.md, section 15](docs/correlation-and-risk-design.md#15-review-and-open-questions)
- [response-workflow-spec.md, section 13](docs/response-workflow-spec.md#13-agreement-checklist-and-open-questions)
- [auth-and-threat-model.md, Part C](docs/auth-and-threat-model.md#part-c-open-questions)
- [dataset-profile.md, section 10](docs/dataset-profile.md#10-open-questions-and-review)
- [wireframes.md, section 6](docs/wireframes.md#6-open-questions)
- [countdown-prototype.md, section 8](docs/countdown-prototype.md#8-open-questions-for-c1-and-c5)
- [ai1-analysis-design.md, section 10](docs/ai1-analysis-design.md#10-open-questions)
- [api-upload-jobs.md, section 8](docs/api-upload-jobs.md#8-open-questions)

## Branches and pull requests

`main` is protected: every change goes through a PR with one approval and green CI. Branch names follow `feature/c2-parser`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full rules and [docs/github-setup.md](docs/github-setup.md) for how the repo was configured.

## Project structure

```
icd-platform/
├── backend/
│   ├── app/
│   │   ├── main.py       FastAPI app, /health, upload size guard
│   │   ├── db.py         lazy SQLAlchemy engine, DeclarativeBase
│   │   ├── models.py     tables: uploads, jobs, events, quarantined_records
│   │   ├── settings.py   upload dir, size limit, worker timings (from the environment)
│   │   ├── storage.py    uploaded files on the shared volume
│   │   ├── api/          upload, job and event endpoints, their shapes (schemas.py) and export.py
│   │   ├── ingest/       parser interface and registry (C2 adds parsers), fixture parser
│   │   ├── jobs/         Postgres job queue and the ingest job
│   │   ├── worker/       the worker process: python -m app.worker
│   │   ├── contracts/    the six shared Pydantic contracts v1 (owned by C3) and export.py
│   │   ├── analysis/     AI1: LLM output v0, prompt v0, grounding check, confidence, mapper
│   │   └── llm/          LLMAnalyzer protocol (adapter.py) and MockAnalyzer (mock.py)
│   ├── migrations/       Alembic environment and revisions (0001 baseline, 0002 uploads and jobs)
│   ├── alembic.ini
│   └── tests/            health, LLM mock, label mapping, contracts/, api/ (shapes), jobs/ (upload API and worker), analysis/ (AI1)
├── frontend/             React + Vite + TypeScript dashboard (C4)
│   ├── src/              pages, components, API client, generated contract types, countdown
│   ├── dev/              countdown test server and accuracy script (dev and test only)
│   └── nginx.conf        serves the build and proxies /api and /ws to api
├── contracts/            owned by C3
│   ├── schemas/          generated JSON Schemas, one per contract
│   ├── examples/         one valid synthetic example per contract
│   └── label-mapping.json  dataset labels to EventLabel (owned by C2)
├── tools/ai1/            AI1 HPC probe, model benchmark and synthetic samples
├── docs/                 design documents and notes (see Documentation above); api/ holds the API schemas and examples
├── .github/              CI workflow and PR template
├── docker-compose.yml
├── .env.example          template for local .env (no real secrets)
├── ruff.toml             lint and format rules
└── CONTRIBUTING.md
```
