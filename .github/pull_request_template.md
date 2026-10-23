## Description

<!-- What does this PR change, and why? Link the task ID (e.g. T1-05) and any issue. -->

Task:

## Tests run

<!-- Commands you ran and their result. CI must also be green. -->

- [ ] `ruff check .` and `ruff format --check .`
- [ ] `pytest` (in `backend/`)
- [ ] `docker compose up --build` (if Compose, Dockerfiles or service config changed)

## Affected contracts

<!-- Event, Incident, EvidencePackage, AnalysisReport, ResponseAction, AuditRecord. Any change needs C3 review. -->

- [ ] None
- [ ] Changed (list them, and request a review from C3):

## Checklist

- [ ] No secrets, credentials or real dataset records are committed
- [ ] Any response action stays simulated and labelled as simulated
