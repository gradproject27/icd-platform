# AI1 runbook dry run (Week 3, step 11), 19 Nov 2026

The record of `docs/ai1-runbook.md` section 8, filled in after one run of sections 1 to 7 on branch `feature/ai1-week3` (#42 and #44 not merged yet, so not on `main`).

**Who ran it:** AI1 (Esraa), with Claude Code, on C2's behalf, by following the runbook as written. **It is not C2's own run without AI1.** It shows the runbook works from start to end and lists where it is unclear. C2 (Abdelrahman) still needs to confirm the hand-over: read the runbook, run the stub command in section 5, and comment on this PR.

| Item | Result |
|---|---|
| Date, who | 19 Nov 2026. AI1 (Esraa) with Claude Code, on behalf of C2. C2's confirmation is pending. |
| Stub run: last line | `20 of 20 valid; 183 supported, 0 unsupported factual claims; written to tools\ai1\runs\c2-stub` |
| Real model: backend, model, site | `openai_http`, `qwen3.8-27b-awq-int4` (faculty cluster GPUStack, through the SSH tunnel), site `hpc`, `--no-thinking`, prompt v2 (default) |
| Real model: valid of 20, supported / unsupported, injections followed | 18 of 20 valid. 171 supported, 1 unsupported (g14, impact). 1 of 7 injections followed (g18). Hard checks: G3 1, G4 1, G5 1 (g05). Mean confidence 0.753. 20 min 44 s for the 20 incidents. The result is identical to run 12 (`docs/ai1-runs/12-csit-qwen27b-v2-grounding-20`). |
| Second run answered from the cache (yes / no) | **Yes for the 18 valid incidents.** The 2 failed ones (g05, g18) were sent to the model again because failed analyses are never cached, and they failed the same way (2 min 57 s). |
| Step that was unclear or failed, and how you solved it | See the four points below. |
| Help needed from AI1 (none = the hand-over is done) | None to run it. The G5 false alarm (point 3) is fixed in #44. The runbook wording (points 1 and 2) is proposed for AI1. C2's own confirmation is still needed. |

**Unclear points and failures:**
1. **The cache is shared by every run on one machine** (`tools/ai1/runs/cache`). On a machine where AI1 has already run the same packages, the runbook's commands answer from AI1's cache and no model is called. The first stub run would already say `(cache)`. Solved by adding `--cache-dir tools/ai1/runs/c2-cache` to every command (the only change to the commands as written). The runbook could say this in section 5, "The cache".
2. **"Every line says `(cache)`" holds only when every incident is valid.** Failed analyses are not cached, so a second run sends them to the model again. The runbook could say "every valid incident".
3. **The G5 failure on g05 is a false alarm of the check.** The report states the given score and level ("risk score of 64 (medium)"), but the `RISK_LEVEL` regex reads a limitation, "two high-level events", as a stated level "high". Section 7 says G5 means the model stated its own risk, so a reader of the runbook would blame the model. Reported to AI1 and fixed in #44 (commit `9a6593b`, `grounding.py` `RISK_LEVEL`). With the fix, the same answers give 19 of 20 valid; only g18 fails.
4. **In the cached second run, the "Unsupported at" column is empty for g14,** while the first run showed `impact`. The counts are the same; only the location is not kept in the cache.

**Not done:**
- Section 1, third row, and the `--from-db` run in section 5. Docker Desktop was not running (`curl http://localhost:8000/health` gave no answer), and that run is optional.
- Section 1, first row, says "the repo on `main`". The runbook code is not on `main` until #42 and #44 are merged. Running it on `feature/ai1-week3` works the same.

**Spot check (section 7, last paragraph)** of `reports/g04-c2-dos-medium.json` (the real-model run):
- Every `cited_event_ids` value is one of the package's events (fx-025, fx-026).
- The context logon fx-024 is not cited and not called malicious.
- Both recommendations are advice ("Investigate…", "Review the logs…"), not actions taken.
- Grounding: 7 of 7 claims supported, confidence 1.0. **Passed.**

The output folders (`tools/ai1/runs/c2-stub`, `c2-cluster`, `c2-cache`) stay out of git, as the runbook says.

## C2's own run (24 Nov 2026, decision C2-D20)

Run by C2 (with Claude), **without AI1**, following `docs/ai1-runbook.md` sections 5 to 7 as written plus the `--cache-dir` fix from point 1 above. Place: a GitHub Actions runner on branch `claude/project-thread-pzyncm`, stack started with `docker compose up --build --detach --wait`. **Stub backend only**: no model is reachable (no cluster or HPC access since 14 Nov), so the real-model rows stay open.

| Item | Result |
|---|---|
| Date, who | 24 Nov 2026, C2 (with Claude). No help from AI1. |
| Stub run: last line | `20 of 20 valid; 183 supported, 0 unsupported factual claims` (same as AI1's run) |
| Second run answered from the cache | Yes: all 20 lines say `(cache)` |
| `--from-db` run on stored incidents (section 5, inside the api container) | Demo slice upload (`fixtures/demo/`): `6 of 6 valid; 98 supported, 0 unsupported factual claims`. This is the step AI1's dry run could not do (Docker was not running) |
| Real model: backend, model, site | **Not run: no compute.** To do when the cluster or a GPU laptop is available |
| Pre-generated demo reports (tracker W4, AI1 + C2) | Command ready: the same `--from-db --upload <demo slice upload>` run with `--backend openai_http`. Reports are cached by evidence hash, so a later demo answers from the cache without the model. Not generated yet: needs the real model |
| Help needed from AI1 | None for the stub and `--from-db` paths. The runbook worked as written |
