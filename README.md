# ICD platform

ICD (Intelligent Cyber Defense) ingests security logs, normalizes them into events, correlates them into incidents, scores risk deterministically, and asks an LLM to explain each incident with cited evidence for an analyst. **All response actions are simulated, labelled as simulated, and audited. Nothing touches a real host.**

## Project status

Week 1 is done. This is what is on `main`:

| Workstream | Delivered in Week 1 |
|---|---|
| C1 | Dev environment (Docker Compose, CI) and backend skeleton: `/health`, Alembic baseline, LLM adapter with a mock |
| C3 | The six shared contracts v1 (models, JSON Schemas, examples, tests) and the correlation and risk-score design |
| C4 | Dashboard skeleton: routes, layout, typed API client, health status |
| C5 | The response workflow specification and the authentication approach and threat model |

Not built yet:

- ingestion and parsing (C2);
- the correlation engine and risk-score code (C3, Week 2);
- real LLM backends (AI1); only `mock` exists;
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
| `worker` | background worker (placeholder) | none |
| `db` | PostgreSQL 17 | internal only (`docker compose exec db psql -U icd icd`) |
| `web` | React dashboard (skeleton); nginx also proxies `/api` and `/ws` to `api` | http://localhost:8080 |

Startup order is enforced by healthchecks: `db` becomes healthy, then `api` and `worker` start, then `web` starts once `api` is healthy. Check the state with `docker compose ps`. Every service should show `(healthy)`.

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

Expected result: **212 passed, 1 skipped**. The skipped test is the one that runs `/health` against a real PostgreSQL database; it needs `DATABASE_URL` and runs in CI.

The tests cover:

- the health check, with the database reachable and unreachable;
- the LLM mock: schema-valid output, citations limited to the input event IDs, deterministic output;
- every contract, with valid payloads and with invalid payloads that must be rejected;
- schema drift: the committed JSON Schemas must match the models, and the examples must match the schemas.

CI (`.github/workflows/ci.yml`) runs five jobs on every pull request and every push to `main`:

| Job | What it does |
|---|---|
| `lint` | `ruff check .` and `ruff format --check .` |
| `test` | `alembic upgrade head` and `pytest` against a PostgreSQL service |
| `frontend` | in `frontend/`: `npm ci`, contract types drift check, ESLint, type check, Vitest, production build |
| `secret-scan` | gitleaks over the full git history |
| `compose-smoke` | starts the stack, waits for every healthcheck, calls `/health`, checks the migration revision, and checks that `web` serves the dashboard and proxies `/api/health` |

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

The TypeScript types of the six contracts in `frontend/src/api/contracts/` are generated from `contracts/schemas/` and never edited by hand. After C3 changes a schema, run `npm run contracts:gen` and commit the result; `npm run contracts:check` fails CI if they are out of date.

## Health check

`GET /health` runs `SELECT 1` against the database:

| Database | Status | Body |
|---|---|---|
| reachable | 200 | `{"status":"ok","database":"ok"}` |
| unreachable | 503 | `{"status":"degraded","database":"unavailable"}` |

The engine is created on first use, so the app starts even when `DATABASE_URL` is unset.

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
| [docs/github-setup.md](docs/github-setup.md) | C1 | | GitHub setup: manual steps to create the repo, add members and protect `main` |
| [docs/scope-change-note.md](docs/scope-change-note.md) | C1 | T1-02 | Scope-change note: roadmap vs. approved specification, for the supervisor (draft, not yet sent) |
| [contracts/README.md](contracts/README.md) | C3 | T1-07 | Where the contract models, schemas and examples live; how to regenerate; change rule |
| [CONTRIBUTING.md](CONTRIBUTING.md) | C1 | | Branch names, pull requests, ownership and rules |

## Open team decisions

These are written down but not yet agreed:

| Decision | Who | Where |
|---|---|---|
| Risk weights v0. The decision record is empty; risk scoring (T2-09) does not start until it is filled in. | Whole team | [correlation-and-risk-design.md, section 10](docs/correlation-and-risk-design.md#10-proposed-v0-weights-and-decision-record) |
| Review of EvidencePackage and AnalysisReport (T1-09) | AI1 | [contracts-v1.md, section 8](docs/contracts-v1.md#8-review-questions-for-ai1-t1-09) |
| Agreement on each contract: Event and EvidencePackage (C2); ResponseAction, AuditRecord and Incident (C5); Incident (C1) | C2, C5, C1 | [contracts-v1.md, section 7](docs/contracts-v1.md#7-agreement-checklist) |
| Response window events and countdown contract | C4 | [response-workflow-spec.md, section 7](docs/response-workflow-spec.md#7-the-60-second-window-and-countdown-contract) |
| Same origin for dashboard and API: `web` proxies `/api` and `/ws` to `api`; C1 builds it before T2-15 | C4 | [auth-and-threat-model.md, section A2.14](docs/auth-and-threat-model.md#a214-same-origin-for-dashboard-and-api) |
| Analysis confidence and valid-analysis rules for the freeze | AI1 | [response-workflow-spec.md, section 5](docs/response-workflow-spec.md#5-freeze-preconditions) |

Each document also marks its own proposals "(proposed, needs team agreement)", for example transition T16 "no response needed" in the response workflow. They are listed in each document's open questions:

- [contracts-v1.md, section 9](docs/contracts-v1.md#9-open-questions)
- [correlation-and-risk-design.md, section 15](docs/correlation-and-risk-design.md#15-review-and-open-questions)
- [response-workflow-spec.md, section 13](docs/response-workflow-spec.md#13-agreement-checklist-and-open-questions)
- [auth-and-threat-model.md, Part C](docs/auth-and-threat-model.md#part-c-open-questions)

## Branches and pull requests

`main` is protected: every change goes through a PR with one approval and green CI. Branch names follow `feature/c2-parser`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full rules and [docs/github-setup.md](docs/github-setup.md) for how the repo was configured.

## Project structure

```
icd-platform/
├── backend/
│   ├── app/
│   │   ├── main.py       FastAPI app and /health
│   │   ├── db.py         lazy SQLAlchemy engine, DeclarativeBase
│   │   ├── contracts/    the six shared Pydantic contracts v1 (owned by C3) and export.py
│   │   └── llm/          LLMAnalyzer protocol (adapter.py) and MockAnalyzer (mock.py)
│   ├── migrations/       Alembic environment and revisions (0001 baseline)
│   ├── alembic.ini
│   └── tests/            health, LLM mock, and contracts/ (one file per contract plus schema drift)
├── worker/               background worker (placeholder)
├── frontend/             React + Vite + TypeScript dashboard (C4): skeleton, generated contract types
├── contracts/            owned by C3
│   ├── schemas/          generated JSON Schemas, one per contract
│   └── examples/         one valid synthetic example per contract
├── docs/                 contracts-v1, correlation-and-risk-design, response-workflow-spec,
│                         auth-and-threat-model, github-setup, scope-change-note
├── .github/              CI workflow and PR template
├── docker-compose.yml
├── .env.example          template for local .env (no real secrets)
├── ruff.toml             lint and format rules
└── CONTRIBUTING.md
```
