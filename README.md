# ICD platform

ICD (Intelligent Cyber Defense) ingests security logs, normalizes them into events, correlates them into incidents, scores risk deterministically, and asks an LLM to explain each incident with cited evidence for an analyst. **All response actions are simulated, labelled as simulated, and audited. Nothing touches a real host.**

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the WSL 2 backend (Windows), or Docker Engine with the Compose plugin (Linux)
- [Git](https://git-scm.com/)
- Python 3.12, only if you run lint and tests outside Docker

## Start everything

```powershell
git clone https://github.com/<owner>/icd-platform.git
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
| `web` | dashboard (placeholder until C4 delivers) | http://localhost:8080 |

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
pytest -v
```

Without `DATABASE_URL`, the real-database test is skipped (10 passed, 1 skipped). CI runs the same checks on every pull request against a Postgres service, plus a gitleaks secret scan and a Compose smoke test (`.github/workflows/ci.yml`).

## Health check

`GET /health` runs `SELECT 1` against the database:

| Database | Status | Body |
|---|---|---|
| reachable | 200 | `{"status":"ok","database":"ok"}` |
| unreachable | 503 | `{"status":"degraded","database":"unavailable"}` |

The engine is created on first use, so the app starts even when `DATABASE_URL` is unset.

## Database migrations

The schema is managed by [Alembic](https://alembic.sqlalchemy.org/) in `backend/migrations`. The URL always comes from `DATABASE_URL`; it is never written in `alembic.ini`. The `api` container runs `alembic upgrade head` before it starts uvicorn, so `docker compose up` always brings the schema up to date. Revision `0001` is an empty baseline.

Add ORM models as subclasses of `app.db.Base`, then create a revision:

```powershell
docker compose exec api alembic revision --autogenerate -m "add incidents table"   # then review the file
docker compose exec api alembic upgrade head
docker compose exec db psql -U icd -d icd -tAc "SELECT version_num FROM alembic_version"
```

Files written inside the container are not on your disk, so you can also run Alembic from `backend/` with your venv and `$env:DATABASE_URL` pointing at a reachable database.

## LLM adapter

Everything that needs an incident explanation depends on the `LLMAnalyzer` protocol in `backend/app/llm/adapter.py`, never on a concrete backend:

```python
from app.llm.adapter import get_analyzer, uncited_event_ids

report = get_analyzer().analyze(evidence)  # EvidencePackage -> AnalysisReport
assert uncited_event_ids(report, evidence) == []  # every cited event ID must exist in the evidence
```

`get_analyzer()` picks the backend from `LLM_BACKEND`. Only `mock` exists for now; any other value raises `ValueError`. `MockAnalyzer` (`backend/app/llm/mock.py`) is deterministic, with no clock, randomness or network. It cites only input event IDs, marks its text `[MOCK]` and its recommendations `[SIMULATED]`, so the rest of ICD runs with no LLM or HPC.

The models in `backend/app/llm/contracts.py` are **provisional**: they get replaced by C3's frozen contracts in `contracts/`. Do not define these models anywhere else.

## Branches and pull requests

`main` is protected: every change goes through a PR with one approval and green CI. Branch names follow `feature/c2-parser`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full rules and [docs/github-setup.md](docs/github-setup.md) for how the repo was configured.

## Project structure

```
icd-platform/
├── backend/
│   ├── app/
│   │   ├── main.py     FastAPI app and /health
│   │   ├── db.py       lazy SQLAlchemy engine, DeclarativeBase
│   │   └── llm/        LLMAnalyzer protocol, MockAnalyzer, provisional contracts
│   ├── migrations/     Alembic environment and revisions
│   ├── alembic.ini
│   └── tests/
├── worker/             background worker
├── frontend/           React/Vite dashboard (C4); placeholder for now
├── contracts/          shared Pydantic contracts (owned by C3)
├── docs/               project documentation and notes
├── .github/            CI workflow and PR template
├── docker-compose.yml
├── .env.example        template for local .env (no real secrets)
├── ruff.toml           lint and format rules
└── CONTRIBUTING.md
```
