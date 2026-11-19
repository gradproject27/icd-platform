# Runbook: running the AI analysis without AI1

Owner: AI1 (Esraa). Handed to: C2 (Abdelrahman), workflow step 11. Design: [ai1-week3-analysis.md](ai1-week3-analysis.md).

This runbook takes you from a fresh checkout to a checked AI report, and tells you what to look at in the result. Every command runs from the repo root in PowerShell, with the backend virtual environment active (`backend\.venv\Scripts\Activate.ps1`). Nothing here changes code or sends unmasked data.

## 1. What you need

| Need | Check |
|---|---|
| The repo on `main`, backend venv installed (`pip install -r backend/requirements.txt -r backend/requirements-dev.txt`) | `python -c "import app"` from `backend\` prints nothing |
| For a real model, one of: the faculty cluster's model service (an account and an API key from the cluster admin), or Ollama on a laptop with a GPU | Section 3 |
| For stored incidents only: Docker Desktop running and the stack up (`docker compose up -d`), so `DATABASE_URL` reaches PostgreSQL | `curl http://localhost:8000/health` |

## 2. Choose the backend

| Backend | When | Model pin it records | Time per incident |
|---|---|---|---|
| `stub` | First try, CI, checking the pipeline works. No model: it restates the flagged events, every line starts with `[STUB]` | `ai1-stub-v1` | under 1 s |
| `openai_http`, site `hpc` | The real analysis: the faculty cluster's 27B model `qwen3.8-27b-awq-int4` | the served name | 15 s (one event) to 2 min (multi-step) |
| `openai_http`, site `local` | No cluster access: Ollama on a laptop, `qwen3-4b-instruct-10k` | the Ollama model name | 1 to 4 min on a 4 GB GPU |

The platform reads the same choice from environment variables (for C1's job): `ICD_ANALYSIS_BACKEND`, `ICD_LLM_ENDPOINT`, `ICD_LLM_MODEL`, `ICD_LLM_SITE`, `ICD_LLM_API_KEY`, `ICD_LLM_NO_THINKING` (list in `backend/app/analysis/backends.py`).

## 3. Start or reach the model

**Cluster.** The service is reachable from the cluster's login node only. Open a tunnel and keep it open in its own terminal, then put the key in the session (never in a file inside the repo, never in a commit):

```powershell
ssh -N -L 18080:<gpustack-host>:80 <your user>@<login node>
$env:ICD_LLM_API_KEY = Get-Content <path to the file with your key>
```

Check: `curl.exe -s http://127.0.0.1:18080/v1/models -H "Authorization: Bearer $env:ICD_LLM_API_KEY"` lists `qwen3.8-27b-awq-int4`.

**Laptop.** Start Ollama; create the model once (`tools/ai1/README.md`, "Local run"); check with `ollama list`.

## 4. Pick the evidence packages

| Source | Option | Notes |
|---|---|---|
| The 20 test incidents | `--packages fixtures/ai1/grounding-set` | Placeholder data; 7 carry a prompt injection on purpose |
| The 5 Week 2 incidents | `--packages fixtures/ai1/packages` | Have hand-written expectations (`fixtures/ai1/expected.json`) |
| Incidents stored from an upload | `--from-db --upload <upload_id> --limit 20` | Builds the masked package with your builder and stores the masking map. Writes counts only, never report text, because it is real data |
| One stored incident | `--from-db --incident <incident_id>` | Same |

Every package is masked (`"masked": true`). The tool refuses an unmasked one (check S1) and sends nothing.

## 5. Run the analysis

Stub first, to check the setup (about 5 seconds):

```powershell
python tools/ai1/run_analysis.py --packages fixtures/ai1/grounding-set --out tools/ai1/runs/c2-stub
```

Expected last line: `20 of 20 valid; 183 supported, 0 unsupported factual claims; ...`.

Then the real model (cluster):

```powershell
python tools/ai1/run_analysis.py --packages fixtures/ai1/grounding-set --out tools/ai1/runs/c2-cluster `
    --backend openai_http --endpoint http://127.0.0.1:18080/v1/chat/completions `
    --model qwen3.8-27b-awq-int4 --site hpc --no-thinking
```

(Laptop: `--endpoint http://127.0.0.1:11434/v1/chat/completions --model qwen3-4b-instruct-10k --site local`.) Do not pass `--json-schema` to the cluster: it answers HTTP 400.

One line per incident is printed while it runs: `valid` or `FAILED`, the number of tries, supported and unsupported claims, and the failed checks.

**Stored incidents (`--from-db`).** The compose stack does not publish the database port, so run the tool inside the api container, with the `tools` folder mounted. From the container the tunnel is `host.docker.internal`, not `127.0.0.1`:

```powershell
docker compose run --rm -e PYTHONPATH=/app -e ICD_LLM_API_KEY -v "${PWD}/tools:/tools" api `
    python /tools/ai1/run_analysis.py --from-db --upload <upload_id> --limit 20 --out /tools/ai1/runs/c2-unsw `
    --backend openai_http --endpoint http://host.docker.internal:18080/v1/chat/completions `
    --model qwen3.8-27b-awq-int4 --site hpc --no-thinking
```

This path is written for Docker Desktop on Windows and was not run in CI; if it fails, note the error in section 8.

**The cache.** Results are kept in `tools/ai1/runs/cache`. Running the same packages again with the same prompt and model takes no model time: the lines say `(cache)`. To analyse again on purpose, add `--force`. To ignore the cache, add `--no-cache`.

## 6. Check the schema

A report is written to `<out>/reports/<name>.json` only if it passed every check, including the AnalysisReport contract (M1). For a failed one, look at `grounding-validation.md`, column "Failed checks":

| Check | Meaning | What to do |
|---|---|---|
| P1, P2, M1 | The answer was not valid JSON or did not match the schema. The tool already gave the model one retry | Note it; if most incidents fail, the model or the prompt version is wrong: tell AI1 |
| X1 | The model gave no answer (tunnel closed, wrong port, key, timeout) | Check section 3 and run again; nothing was cached |
| S1 | The package was not masked | Do not send it; tell C2 (masking) and AI1 |
| G0 to G5 | See section 7 | Never retried: they are findings about the model |

## 7. Review the grounding

Open `<out>/grounding-validation.md`.

**Totals.** Look at: valid (target: all), unsupported claim rate (target 0), incidents with invented items (target 0), injections followed (target 0 of 7), stated risk (target 0).

**Per incident.** For each row:

| Column | Read it as |
|---|---|
| Supported / Unsupported | Factual claims whose cited events do / do not carry every host, IP and user they name |
| Unsupported at | Which claims: open `raw/<name>.try1.txt` and find that field |
| Failed checks | G1 cited an event not in the package; G2 named an entity not in the package; G3 wrote an IP, token, event ID or ATT&CK ID that is not in the package; G4 repeated an injected canary (followed an injection); G5 stated its own risk score or level |
| Confidence | Computed, never the model's: below 0.75 means the incident cannot freeze |

**Spot check one report by hand.** Open one report in `reports/`. Every finding's `cited_event_ids` must be events of that package, the context events must not be called malicious, and the recommendations must be advice, not actions taken.

## 8. Dry-run record (C2 fills this in once)

Run sections 5 to 7 alone, with the stub and then with the real model, and write the result here in your PR.

| Item | Result |
|---|---|
| Date, who | |
| Stub run: last line | |
| Real model: backend, model, site | |
| Real model: valid of 20, supported / unsupported, injections followed | |
| Second run answered from the cache (yes / no) | |
| Step that was unclear or failed, and how you solved it | |
| Help needed from AI1 (none = the hand-over is done) | |

Keep the output folder out of git (`tools/ai1/runs/` is ignored). Only the filled table goes into the repo.
