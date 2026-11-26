# Demo replay: the 27B model's answers without the cluster (AI1 + C2, tracker task 31)

| | |
|---|---|
| **Owners** | AI1 (recording, backend), C2 (demo data) |
| **Code** | `backend/app/analysis/replay.py`; tests `backend/tests/analysis/test_replay.py`, `backend/tests/jobs/test_replay_demo.py` (Postgres, CI) |
| **Recordings** | `backend/app/analysis/replay_data/*.json` (inside the image) |
| **Decisions** | AI1-W4-D1 to D4 (proposed), [decision-log.md](decision-log.md) |

## 1. Why the report cache could not do this

The plan was to pre-generate reports on the cluster and serve them from the report cache. That never works in the demo:

| Reason | Where |
|---|---|
| The demo reset empties every table, `analysis_reports` included | C1, `app/demo/reset.py` (F9) |
| Incident IDs are scoped to the upload, and the cache key holds the package (with its incident ID) | C3/C1 D4; AI1-W3-D5 |
| The cache key holds the model pin, so the stub fallback never matches a 27B report | AI1-W3-D5 |

## 2. How replay works

- **Key (AI1-W4-D1).** The SHA-256 of the masked evidence package without `incident_id`, `package_id` and `created_at`, plus the prompt version. The same events, risk and masking give the same key in every upload.
- **Answer.** The model's final raw answer, stored with its incident ID written as `{{incident_id}}`. Replay puts the current ID back. The key already proves the answer was written for these exact events.
- **Same checks as live.** The worker sends the replayed text through the analysis service: schema, grounding, confidence, and C5's freeze gate. Nothing on the safety path is skipped. One try, since a repair turn would get the same text back.
- **Honesty (AI1-W4-D2).** The report's model is `replay:<recorded model>`, shown on the report page. `generated_by` is the site that really ran the model.
- **Failures stay failures (AI1-W4-D3).** An answer that failed the checks during recording is replayed and fails again, so the analysis shows as failed and nothing freezes. An incident the model never answered replays as a backend error. A file with no recording fails its analyses. The stub never stands in.

## 3. Record (once, with the cluster)

Only the backend Python environment and the cluster tunnel are needed: no Docker (AI1-W4-D4). From `backend/`:

```powershell
# The cluster model, as in ai1-runbook.md section 2 (the key in your shell only, never committed)
$env:ICD_ANALYSIS_BACKEND = "openai_http"
$env:ICD_LLM_ENDPOINT = "http://127.0.0.1:<tunnel port>/v1/chat/completions"
$env:ICD_LLM_MODEL = "<served model name>"
$env:ICD_LLM_SITE = "hpc"
$env:ICD_LLM_NO_THINKING = "1"
$env:ICD_LLM_API_KEY = "<key>"

python -m app.analysis.replay record fixture ../fixtures/correlation/events.json --out app/analysis/replay_data/fixture.json
python -m app.analysis.replay record unsw-nb15 ../data/demo/unsw-nb15-demo-slice.csv --out app/analysis/replay_data/unsw-nb15-demo-slice.json
python -m app.analysis.replay check     # what the worker will load
```

Build the demo slice first ([fixtures/demo/README.md](../fixtures/demo/README.md)). It must print "matches", or its incidents will not match the recording.

**How `record` matches the platform.** It builds each incident's package the way the worker does:
- C2's parser, with quarantined lines and repeated event IDs left out;
- C3's correlation, scoped to one upload;
- risk over the whole upload, with clock W = its latest event time;
- C2's masked builder.

It then calls the model through the analysis service with the same tries as the analysis job (prompt v2, one schema retry). `test_offline_recording_is_replayed_by_the_platform` proves this in CI: it records offline, uploads the same file to the platform, and every incident finds its recording. With a running platform, `python -m app.analysis.replay export --upload <id>` records the stored valid reports instead.

**Output cap.** Record with the app default of 8,000 tokens (AI1-W4-D5). At 4,900 the answer for the slice's largest incident was cut off mid-JSON.

**What to commit.** The two JSON files. They hold masked answers only (tokens such as `ip-01`, no real IP, host or user), the same kind of text as `docs/ai1-runs/`. Note the result line ("N incidents: V valid, F failed") in the PR.

## 4. Recorded on 26 Nov 2026

The 27B model `qwen3.8-27b-awq-int4` on the faculty's GPUStack service, prompt v2, temperature 0, thinking off. Recorded on the workstation `csit-csc`; the files hold masked answers only (no IP, host or user values).

| File | Incidents | Valid | Freezes in the demo |
|---|---|---|---|
| `fixture.json` (C3's fixture, output cap 4,900) | 13 | 13, all on the first try | **1**: Backdoors, risk 100 High, confidence 0.93 (paths A and B) |
| `unsw-nb15-demo-slice.json` (C2's slice, checksum matches; output cap 8,000) | 6 | 6, all on the first try | **0**: the two High incidents (DoS 99 and DoS 70) have confidence 0.73 and 0.0, under the 0.75 gate |

The first slice recording at 4,900 tokens cut the DoS 99 answer off mid-JSON (P1, both tries); the slice was recorded again at 8,000 (AI1-W4-D5). On UNSW data the real model, like the stub, does not reach the freeze threshold: paths A and B are shown with the fixture, and the UNSW slice shows real-data incidents with real-model reports that wait for a human.

## 5. Use in the demo

`.env`: `ICD_ANALYSIS_BACKEND=replay`, then `docker compose up -d --build worker` (the recordings are in the image) and the demo reset. Steps: [demo-script.md](demo-script.md) §0.

## 6. Limits

- Only the recorded files have answers.
- A recording is tied to the prompt version, the risk configuration and the masking. A change to any of them changes the keys, and the worker then fails those incidents: record again.
- The worker refuses recordings from two different models, or for an older prompt, at start-up.
