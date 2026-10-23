# Contributing

## Branches

`main` is protected. Nobody pushes to it directly; all work goes through a pull request.

Name branches `<type>/<workstream>-<short-topic>`:

| Type | Use | Example |
|---|---|---|
| `feature/` | new functionality | `feature/c2-parser` |
| `fix/` | bug fix | `fix/c3-window-boundary` |
| `docs/` | documentation only | `docs/c5-threat-model` |
| `chore/` | tooling, CI, dependencies | `chore/c1-ci-cache` |

Workstream prefixes: `c1` to `c5`, `ai1`.

## Pull requests

1. Branch from the latest `main`: `git switch main && git pull && git switch -c feature/c2-parser`.
2. Keep PRs small, one task per PR where possible.
3. Fill in the PR template (description, tests run, affected contracts).
4. CI must be green (lint, tests, secret scan, Compose smoke test).
5. At least one approving review from another member is required. A change to `contracts/` also needs C3's review.
6. Merge with **Squash and merge**, then delete the branch.

## Ownership

| Area | Owner |
|---|---|
| Repo, CI, Docker Compose, `backend/app` skeleton, LLM adapter interface | C1 |
| Ingestion, parsing, evidence package construction | C2 |
| `contracts/`, correlation, incidents, risk scoring | C3 |
| `frontend/` | C4 |
| Response workflow, security, QA | C5 |
| Prompts, report schema, AI evaluation | AI1 |

## Rules

- Never commit secrets. `.env` is git-ignored; only `.env.example` is committed, with placeholder values.
- Never commit real dataset records. Use small synthetic fixtures in tests.
- Response actions are simulated only and must never touch a real host.
- Pin dependency versions in `requirements*.txt`.
