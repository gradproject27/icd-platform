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
python -m venv .venv
.venv\Scripts\Activate.ps1       # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cd ..
ruff check .
ruff format --check .
cd backend
pytest -v
```

CI runs the same checks on every pull request, plus a gitleaks secret scan and a Compose smoke test (`.github/workflows/ci.yml`).

## Branches and pull requests

`main` is protected: every change goes through a PR with one approval and green CI. Branch names follow `feature/c2-parser`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full rules and [docs/github-setup.md](docs/github-setup.md) for how the repo was configured.

## Project structure

```
icd-platform/
├── backend/            FastAPI app (app/) and its tests (tests/)
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

