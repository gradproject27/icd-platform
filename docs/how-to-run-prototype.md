# How to run the ICD prototype

| | |
|---|---|
| **Owner** | C1 (Platform and Integration) |
| **Status** | 24 Nov 2026, checked on `main` after PRs #46 to #49 |
| **What it is** | The initial prototype of the full ICD system: one `docker compose` stack that goes from an uploaded log file to a stored, analysed, risk-scored incident, a freeze with a 60-second response window, and a simulated response with a full audit trail |

Every response action is **simulated** and labelled `SIMULATED`. Nothing touches a real host.

## 1. What you need

- Docker Desktop (Windows, WSL 2 backend) or Docker Engine with the Compose plugin (Linux).
- Git.
- Python 3.12 or later on the host, only for the helper scripts in `tools/`. `tools/c1/demo_reset.py` and `tools/c2/demo_edge_cases.py` need the standard library only; `tools/c2/make_demo_slice.py` (section 6) also needs the backend packages.
- About 3 GB of free disk for the images.

## 2. Start the stack (about 3 minutes the first time)

```powershell
git clone https://github.com/gradproject27/icd-platform.git
cd icd-platform
Copy-Item .env.example .env          # Linux/macOS: cp .env.example .env
docker compose up --build --detach --wait
docker compose ps                    # db, api, worker and web all "(healthy)"
```

Open http://localhost:8080. The header shows **API online**. The API's own docs are at http://localhost:8000/docs.

`.env.example` already holds what the demo needs: `ICD_ANALYSIS_BACKEND=stub` (no model needed) and the development analyst `ICD_DEV_USER=analyst-dev`, `ICD_DEV_ROLE=soc_analyst`. Without these two, every decision is refused with 403 because login is not built yet (T2-15).

## 3. Reset to a clean demo state

```powershell
python tools/c1/demo_reset.py --no-upload
```

It stops the worker, empties every app table and stored upload (the schema stays), and starts the worker again. Use `--no-upload` before a live demo, so the High incident's 60-second window opens only when you upload in front of the audience.

Without `--no-upload` the reset also uploads the C3 fixture and waits until every incident is analysed. Expected output (24 Nov 2026): `13 incidents, 1 with an open response window`.

## 4. Demo path A: the analyst decides in time

1. **Upload** (`/upload`): dataset source **Synthetic fixture (JSON list of Events)**, file `fixtures/correlation/events.json`, click Upload. The steps go Uploaded, Validating, Parsing, Correlating, Done; the intake summary shows 43 records read, 43 stored, 0 quarantined.
2. **Incidents** (`/incidents`): 13 incidents. One Backdoors incident is **High 100** and is in **Awaiting Human Decision**.
3. **AI report** (`/incidents/<id>/report`): risk 100/100, High, confidence 93%, the grounding line ("19 of 19 factual claims supported by their cited events"), and the report sections with cited event IDs. With the stub model the report says so (`[MOCK REPORT]`, `[STUB]`).
4. **Pending decision** (`/incidents/<id>/decision`): the countdown runs from the server's deadline; "Simulated isolation is active [SIMULATED]"; recommended **S2** (isolate the host and block the source IP).
5. Within 60 seconds choose **Approve recommended action (S2, SIMULATED)**, then **Review decision**, then **Submit decision**. The incident becomes **Resolved**, the action is simulated and succeeded.
6. **Audit** (`/incidents/<id>/audit`): `Decision recorded` by `analyst-dev (SOC Analyst)`, then `Action simulated [SIMULATED]` with trigger `analyst_decision`. After the deadline nothing else is added (the window is `decided`).

## 5. Demo path B: nobody decides, the system selects

1. `python tools/c1/demo_reset.py --no-upload`, then repeat steps 1 to 4 of path A.
2. Do nothing. When the countdown reaches 0 the page shows "Window expired … The system selects a scenario (SIMULATED)", then "Selected by the system at the deadline", **S2**, status **Resolved**.
3. **Audit**: `Response window expired` ("the response window expired without an analyst decision"), `Scenario selected` by `system`, `Action simulated [SIMULATED]` with trigger `window_expiry`.

The full talk track, the variations (Reject, Select another scenario, a late decision refused with 409) and the stage fallbacks are in [demo-script.md](demo-script.md). The rehearsal record with screenshots' content and audit rows is [demo-runs/2026-11-24-paths-a-b.md](demo-runs/2026-11-24-paths-a-b.md).

## 6. Optional: the real UNSW-NB15 demo slice

The demo slice is 86 lines of the official `UNSW-NB15_1.csv`. Dataset rows are never committed, so build it from the official file and check its SHA-256 against the committed manifest ([fixtures/demo/README.md](../fixtures/demo/README.md)):

```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt                     # make_demo_slice.py uses the parser and correlation code
python -I tools/c2/unsw_download.py UNSW-NB15_1.csv --out data/
python tools/c2/make_demo_slice.py rebuild data/UNSW-NB15_1.csv --out demo/    # prints "matches"
python tools/c1/demo_reset.py --file demo/unsw-nb15-demo-slice.csv --dataset-id unsw-nb15
python tools/c2/demo_edge_cases.py demo/unsw-nb15-demo-slice.csv               # duplicate 409, malformed rows quarantined
```

The slice gives 6 incidents: High 2, Medium 2, Low 2 (`fixtures/demo/unsw-nb15-demo-slice.json`). With the stub model none of them freezes: both High incidents get confidence 0.73, under the 0.75 threshold, so they wait for a human without a timer. That is the safety rule; a freeze on UNSW data needs a real model's confidence. Show paths A and B with the fixture (sections 4 and 5). Details: rehearsal record, section 4.

## 7. Using a real model instead of the stub

Set `ICD_ANALYSIS_BACKEND` in `.env` and restart the worker (`docker compose up -d worker`):

| Backend | When | Variables |
|---|---|---|
| `stub` (default) | No compute; demos and CI | none |
| `openai_http` | Ollama on a laptop, or the faculty cluster's model service through its SSH tunnel ([ai1-runbook.md](ai1-runbook.md) §3) | `ICD_LLM_ENDPOINT` (from the container use `host.docker.internal`), `ICD_LLM_MODEL`, `ICD_LLM_API_KEY` if needed |
| `hpc_batch` | Slurm cluster over ssh (`tools/c1/icd_analyze.sbatch`) | `ICD_HPC_*`; built and tested against a fake cluster only, not yet run on a real HPC |
| `replay` | The demo without the cluster: the 27B model's recorded answers for the fixture and the demo slice ([ai1-demo-replay.md](ai1-demo-replay.md)) | `ICD_REPLAY_FILES` (optional; default every file in `backend/app/analysis/replay_data/`) |

Real-model runs have not been made inside the app yet because no compute is available; the AI1 model runs in `docs/ai1-runs/` were made with AI1's tools.

## 8. Stop, wipe, and check

```powershell
docker compose down              # stop, keep the data
docker compose down --volumes    # stop and wipe the database and uploads
```

Tests (CI runs the same): see [README.md, Lint and tests](../README.md#lint-and-tests).

## 9. If something goes wrong

| Problem | What to do |
|---|---|
| A service is not `(healthy)` | `docker compose logs api worker` ; the api applies the migrations before it reports healthy |
| Port 8000 or 8080 in use | Change `API_PORT` / `WEB_PORT` in `.env` |
| Decision refused with 403 | `ICD_DEV_USER` / `ICD_DEV_ROLE` missing in `.env`; then `docker compose up -d api` |
| Upload refused with 409 `duplicate_upload` | The same file was already uploaded; run the reset first |
| No countdown on the High incident | Open its audit trail: the last `Status changed` lists the failed freeze preconditions in `reasons` |
| The window expired before the audience saw it | You ran the reset without `--no-upload`; reset with `--no-upload` and upload live |
| Building the image fails at `apt-get` | The backend image installs `openssh-client` (needed only for `hpc_batch`); the build needs access to `deb.debian.org` |
