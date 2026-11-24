# Prototype demo script: paths A and B (C5, tracker task 30)

| | |
|---|---|
| **Owner** | C5 (Response and Security) |
| **Status** | v1, 24 Nov 2026 (decision C5-D4). Rehearsal is tracker task 25 (all members) |
| **Backed by** | `backend/tests/response/test_demo_paths_db.py` (Postgres): the same steps, from stored events to the simulated action, pass in CI |
| **Depends on** | C1's analysis job and demo reset (PR #47: registers incidents with the response engine and runs the analysis after correlation; `tools/c1/demo_reset.py`). Until #47 is on `main`, steps 3 to 5 cannot be shown in the browser; the test above shows them. Checked 24 Nov: this branch merged with #47 passes all 1,025 backend tests |

The demo shows the one thing that makes ICD different: a High, confidently analysed incident **freezes** (the host is isolated, simulated) and a **60-second response window** opens. Then either an analyst decides in time (path A) or nobody does and the system selects the recommended scenario at the deadline (path B). Every action is **simulated**; nothing reaches a real system.

## 0. Before the audience arrives

1. `cp .env.example .env` and check `ICD_DEV_USER=analyst-dev`, `ICD_DEV_ROLE=soc_analyst` (until login exists, decisions are made as this identity; without it every decision is refused with 403).
2. Choose the model:
   - **HPC/cluster available:** set the backend the runbook names ([ai1-runbook.md](ai1-runbook.md) §2 and §3).
   - **HPC fallback (default for the demo):** keep `LLM_BACKEND=mock`. The stub model gives schema-valid reports with computed confidence; reports already made on the cluster are served from the report cache (`analysis_reports`, [ai1-runbook.md](ai1-runbook.md)) when the evidence is unchanged. Say this out loud: the analysis is real code, the model is the stand-in.
3. Start the stack (`docker compose up -d --build --wait`), then reset with C1's command: `python tools/c1/demo_reset.py --no-upload` (empties every app table and stored upload; the schema stays). Use `--no-upload` for the live demo: without it the reset uploads the fixture itself and incident A's 60-second window opens at once, before the audience sees the upload. Without C1's tool (before PR #47 is merged): `docker compose down --volumes && docker compose up --build`.
4. Open http://localhost:8080 in one window and keep a terminal open.

## 1. Data used

`fixtures/correlation/events.json` (dataset `fixture`). It gives 13 incidents. With the stub model, exactly one freezes, which is what the demo needs (output of the test's pipeline on 24 Nov):

| Incident starts at | Risk | Confidence | Freezes? | Why not |
|---|---|---|---|---|
| **fx-002 (incident A, Backdoors)** | **High (100)** | **0.93** | **yes** | |
| fx-038 (Backdoors) | High (96) | 0.73 | no | confidence below 0.75 (OD-16) |
| fx-025 (DoS) | Medium | 1.00 | no | risk not High |
| other 10 | Low/Medium | 0.60 to 0.87 | no | risk not High (and some low confidence) |

Incident A's targets: host `web-01`, external source IP `203.0.113.10`, account `svc-db` → recommended scenario **S2** (isolate the host and block the source IP).

With a UNSW-NB15 file instead (`unsw-nb15`), incidents can freeze too since config `response-v1`: the victim (`149.171.126.0/24`) becomes the host and the attacker (`175.45.176.0/24`) the source IP ([response-engine.md](response-engine.md) §3).

## 2. Common opening (both paths), about 2 minutes

| Step | Screen | Do | Say |
|---|---|---|---|
| 1 | `/upload` | Choose dataset `fixture`, file `fixtures/correlation/events.json`, upload | Logs are parsed, normalised and labelled; bad rows are quarantined with a reason |
| 2 | `/upload?job=…` | Wait for `done` | The worker stored the events, then C3 correlated them into incidents and scored each one |
| 3 | `/incidents` | Point at incident A (High) and at fx-038 (also High) | The risk score is explainable: open "why grouped" if asked |
| 4 | `/incidents/<A>/report` | Show the AI report | Masked evidence went to the model; the report is checked against the evidence (grounding) and gets a confidence |
| 5 | `/incidents/<A>/decision` | The countdown is running | High risk + valid report + confidence ≥ 0.75 → **freeze**. `web-01` is isolated `[SIMULATED]`. The deadline is held by the server, not the browser |

Then show that fx-038 did **not** freeze (its decision page has no countdown): same High risk, but confidence 0.73 is under the threshold, so a human decides with no timer. This is the safety rule (FR-43, OD-16).

## 3. Path A: the analyst decides in time (about 1 minute)

| Step | Screen | Do | Expected |
|---|---|---|---|
| A1 | `/incidents/<A>/decision` | Within 60 s, click **Approve recommended action (S2, SIMULATED)** | Status `resolved`; action S2 `simulated_succeeded`, trigger `analyst_decision`, decided by `analyst-dev` |
| A2 | same | Wait past the deadline | Nothing else happens: the window is `decided`, expiry selects nothing |
| A3 | `/incidents/<A>/audit` | Scroll the trail | `status_changed` (New, Under Analysis, Awaiting with cause "freeze started"), `action.simulated` (isolation), `response_window.opened`, `decision.recorded`, `action.simulated` (S2) with label `SIMULATED` |

Variations if asked: **Reject** releases the isolation and keeps the incident open for a human; **Select** another scenario (S1, S3 or S4); a decision one millisecond after the deadline is refused (409).

## 4. Path B: nobody decides, the system selects (about 1.5 minutes)

Reset (step 0.3) and repeat steps 1 to 5. Then:

| Step | Screen | Do | Expected |
|---|---|---|---|
| B1 | `/incidents/<A>/decision` | Do nothing; let the countdown reach 0 | Within about a second the page shows the window `expired` |
| B2 | same | | Status `resolved`; action S2, trigger `window_expiry`, decided by `system`, `[SIMULATED]` |
| B3 | `/incidents/<A>/audit` | | `response_window.expired` ("expired with no analyst decision"), `scenario.selected` with incident type, confidence band and targets, `action.simulated` |
| B4 | terminal (optional) | `docker compose restart worker` while a window is open, then wait | After restart the overdue window is expired **once**: the expiry is safe across restarts and between two workers |

Say: the system only selects automatically after the deadline, only from the approved catalogue, never S4 (release isolation), and if no scenario fits it escalates to a human and runs nothing.

## 5. If something goes wrong on stage

| Problem | Fallback |
|---|---|
| Model/HPC unreachable | `LLM_BACKEND=mock` (step 0.2). The incident still freezes; the report says it came from the stub |
| Decision refused with 403 | `ICD_DEV_USER`/`ICD_DEV_ROLE` missing in `.env`; restart `api` |
| No countdown on incident A | In the incident's audit trail, the `status_changed` record with cause "analysed, no freeze" lists the failed preconditions in `reasons` (e.g. `analysis_not_valid`, `confidence_below_threshold`, `no_target_host`) |
| Browser shows a stale countdown | Refresh: the page reads the deadline from the server again |
| Nothing works in the browser | From `backend/` with Postgres reachable: `DATABASE_URL=… pytest -q tests/response/test_demo_paths_db.py` (the `api` image has no tests). It runs the same paths from stored events to the simulated action |

## 6. What the demo does not claim

- No real system is touched: every action is labelled `SIMULATED` (response spec §10).
- Login is not built yet (planned T2-15); the analyst is the development identity.
- The 30-second reminder (OD-19) is not built (W5).
- The response catalogue is v0 (OD-20, formal approval W7).
