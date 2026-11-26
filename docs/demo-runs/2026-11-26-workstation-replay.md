# Prototype run with the 27B model's answers, on the faculty workstation (26 Nov 2026)

| | |
|---|---|
| **Tracker tasks** | 31 (cached AI fallback), 25 (demo paths), M3 (real-dataset incidents with real-model reports), M4 (prototype) |
| **Code** | branch `feature/ai1-demo-replay` at `3389ed6` (`main` at `c5a17ae` + the replay backend and its recordings) |
| **Where** | CSIT compute pool, login node `csit-csc`, rootless Podman 4.9.3 with Docker Compose v5.7.2 (allowed by the pool's user guide; no admin rights) |
| **Model** | `ICD_ANALYSIS_BACKEND=replay`: the answers of `qwen3.8-27b-awq-int4` (faculty GPUStack service, prompt v2, temperature 0, thinking off), recorded the same day ([ai1-demo-replay.md](../ai1-demo-replay.md) §4) |
| **Result** | **Both demo files run end to end with real-model reports; path B completes on its own.** No database edit; every step through the API and C1's reset tool |

## 1. Why the workstation

Docker Desktop could not run on the team laptop: its Windows build (10.0.21996, a 2021 preview) rejects the virtual machine current WSL creates (`HCS_E_INVALID_JSON`). The pool's login node has rootless Podman, and its user guide allows containers.

Setup, all in the user's account:
- container storage on the node's local disk (`/local/<user>`), because the shared `/pool` file system is a poor fit for a database;
- Podman's user socket, so Compose and `tools/c1/demo_reset.py` work unchanged through `DOCKER_HOST`;
- in `.env`: `ICD_ANALYSIS_BACKEND=replay`, a random local database password, and the ports bound to `127.0.0.1` only (dashboard 18080, API 18000; port 8080 on the node is taken). The analyst opens the dashboard through an SSH tunnel: `ssh -N -L 8080:127.0.0.1:18080 <user>@<login node>`, then http://localhost:8080.

**One Podman difference.** Podman splits an exec-form health-check argument at its spaces. The API's check (`python -c "import urllib.request; …"`) therefore ran as `python -c import` and failed, although the API answered `/health` with `{"status":"ok","database":"ok"}`. A local `docker-compose.override.yml` runs the same check through the shell (`CMD-SHELL`). After that, all four services were healthy. This is not fixed in the repo (follow-up below).

## 2. Fixture (`fixtures/correlation/events.json`, dataset `fixture`)

`python tools/c1/demo_reset.py --base-url http://127.0.0.1:18080/api`:

| Step | Result |
|---|---|
| Ingest | 43 records read, 43 stored (24 flagged, 17 unflagged, 2 unlabelled), 0 quarantined |
| Correlation and risk | 13 incidents: High 2, Medium 4, Low 7 |
| AI analysis (replay) | **13 of 13 succeeded** in about 2 s |
| Freeze | **1 response window**: incident A (Backdoors, High, confidence 0.9333) |

Incident A's report: model `replay:qwen3.8-27b-awq-int4`, site `hpc`, grounding 18 of 18 factual claims supported (0 unsupported).

Confidences: 0.9333 (A, High, froze); 0.7333 for the other High incident and 7 more; 1.0, 0.8667; 0.0 for two Medium incidents (the model reported insufficient evidence). Only A meets High and confidence ≥ 0.75, as with the stub model.

**Path B (nobody decides).** The reset uploads the fixture itself, so A's 60-second window opened with nobody deciding. Its audit trail, in order:
1. `status_changed` × 3 (new, under analysis, awaiting human decision)
2. `action.simulated` (isolation, label SIMULATED)
3. `response_window.opened`
4. `notification.sent`
5. `response_window.expired`
6. `scenario.selected` by `system`
7. `status_changed`
8. `action.simulated` (label SIMULATED)
9. `status_changed`

## 3. UNSW-NB15 demo slice (C2's 86 lines of `UNSW-NB15_1.csv`, dataset `unsw-nb15`)

The slice was rebuilt from the official file on the workstation: SHA-256 `918163c0…c2e5e9`, which **matches** `fixtures/demo/unsw-nb15-demo-slice.sha256`.

`demo_reset.py --file data/demo/unsw-nb15-demo-slice.csv --dataset-id unsw-nb15`:

| Incident risk | Analysis | Confidence | Window |
|---|---|---|---|
| High | succeeded | 0.0 | no |
| High | succeeded | 0.7333 | no |
| Medium | succeeded | 0.0 | no |
| Medium | succeeded | 0.7333 | no |
| Low | succeeded | 0.7333 | no |
| Low | succeeded | 0.0 | no |

**6 of 6 analysed with real-model reports; none freezes.** Both High incidents stay under the 0.75 confidence gate, so they wait for a human with no timer. That is the safety rule; the stub model gave the same outcome (rehearsal of 24 Nov, §4). Paths A and B stay on the fixture.

The platform was then emptied (`--no-upload`) for a live demo.

## 4. Not covered by this run

- **Path A in the browser.** It was not clicked this time; the 24 Nov rehearsal covers it, and this run changes only the model's answers, not the decision flow.
- **A live model call from the app.** The replay backend answers with recorded text; the answers themselves come from the real model (recorded the same day).
- **C2's edge-case tool** (duplicate 409, malformed lines) was not run on the workstation.
- **The Podman health-check difference** is not fixed in the repo. Proposed follow-up: use `CMD-SHELL` for the API's check in `docker-compose.yml`, which works on both Docker and Podman.
