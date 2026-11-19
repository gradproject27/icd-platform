# AI1 report schema v1: evidence in, report out, HPC files, C5 fields and evaluation

| | |
|---|---|
| **Owner** | AI1 (AI Analysis & Evaluation), Week 2 |
| **Status** | Built and tested with hand-written reference answers. Run on two local models (14 Nov 2026) and on the faculty cluster's 27B model (19 Nov 2026), section 8: 72 valid real reports. Prompt v1 is the default. The draft key-fact scores wait for the team's review |
| **Code** | `backend/app/analysis/` (`output.py`, `pipeline.py`, `handoff.py`, `incident_fields.py`, `metrics.py`, `export.py`), `tools/ai1/` (`icd_analyze.py`, `make_packages.py`, `evaluate.py`, `bench.py`), `fixtures/ai1/` |
| **Schemas** | `contracts/ai1/llm-output-v0.schema.json`, `hpc-output-v1.schema.json`, `expected-incident-v1.schema.json` (generated: `cd backend; python -m app.analysis.export`; a test fails when they are stale) |
| **Agrees with** | C2 and C3 (EvidencePackage and Incident, unchanged; C2-D1 to C2-D7 in `docs/decision-log.md`), C5 (report valid and confidence: `docs/response-engine.md` section 9 and decision D2), C1 (analysis job and its errors: `docs/api-upload-jobs.md`; the HPC transport comes in C1's HPC handoff PR, not on GitHub yet) |
| **Builds on** | `docs/ai1-analysis-design.md` (Week 1: prompts, checks, confidence, HPC checks and model), `docs/evidence-package.md` (C2 builder and masking), `docs/ai1-runs/` (local model runs) |

No shared contract changes. Every AI1 format here maps onto the C3 contracts as they are on `main`.

**Compute resources.** From 14 to 19 Nov 2026 the team had no HPC access, and real runs used the local fallback (Ollama on the team laptop). Since 19 Nov 2026 the faculty's CSIT Compute Pool is available: Slurm on four workstations with RTX 5000 GPUs, and a shared model service (GPUStack) with a 27B model. The HPC checks, the model run and the batch-or-service recommendation are in `docs/ai1-analysis-design.md`, sections 2 to 5. The `transformers` path of `icd_analyze.py` and `run_bench.sbatch` stay tested with the stub only: the service made them unnecessary for now.

## 1. Week 2 tasks

| AI1 Week 2 task | Where | Status |
|---|---|---|
| Define the evidence package shape (agree with C2 and C3) | Section 3. C2's builder (`app/evidence`) produces EvidencePackage 1.0; AI1 needs no new field | Agreed as built |
| Prepare 5 incidents by hand for testing | Section 7, `fixtures/ai1/` | Done: 5 packages, hand-written expectations and reference answers |
| First version of the AI prompt | Prompt v0, `backend/app/analysis/prompts/` (Week 1, rule 12 added after the local runs); v1 after this evaluation (section 8) | Done |
| Check that the entities named exist in the evidence | Checks G1 to G3 and U1 (`grounding.py`) | Done |
| Initial confidence value | `confidence.py`, section 5 | Done |
| 5 AI reports that match the schema | `tools/ai1/evaluate.py` writes one AnalysisReport per valid run to `reports/` | Done: 5 from the reference answers, 42 from two local models and 30 from the cluster's 27B model (section 8) |
| Evaluate the results with defined metrics | Metrics E1 to E11, section 6 | Done: E1 to E11 measured on three models and both prompts (section 8). Draft key-fact scores of the 27 local reports are in a separate PR for the team to review |
| **Handoff to C5:** confidence and report-valid fields | Section 5, `incident_fields.py` | Done; matches C5's decision D2 and `docs/response-engine.md` section 9 |
| **Handoff to C1:** report schema and evidence file format for the HPC | Section 4, `handoff.py`, `icd_analyze.py` | Done; job outcomes follow C1's merged analysis-job rules. C1's HPC transport PR is not on GitHub yet |

## 2. The flow

```
Incident (C3) ─► build_and_store_package (C2) ─► evidence file: EvidencePackage 1.0, masked
      ─► icd_analyze.py on the HPC or a local model: prompt v1 ─► output file: icd-hpc-output-v1
      ─► app host: analyze_hpc_output ─► run_analysis: parse (P1, P2), grounding (G0-G5), confidence, map (M1)
      ─► AnalysisReport 1.0 (stored masked) + apply_result ─► Incident.analysis_status / confidence / latest_report_id
      ─► C5 freeze rule; the dashboard shows unmask_report(report) (C2)
```

## 3. Evidence file (input)

One `EvidencePackage` 1.0 as JSON, exactly the contract (`contracts/schemas/evidence-package.schema.json`), built by C2's `build_package`. AI1 relies on these properties, all enforced by the contract or the builder:

| Property | Why AI1 needs it |
|---|---|
| `masked = true`; host, IP and user values are `host-NN`, `ip-NN`, `user-NN`, one numbering per package | NFR-S-07; the grounding check recognises tokens (`MASKED_TOKEN`). `icd_analyze.py` refuses an unmasked package (exit 2) |
| At most 50 events, all flagged first, then context nearest in time | Prompt rule 12 asks the model to cite every flagged event |
| `role` agrees with `label_status` | Prompt rule 6: context and unlabelled events are never evidence of malice on their own |
| `incident.risk_score` and `risk_level` filled by C3 before the analysis | Prompt rule 8: the model explains the given score and never makes one (OD-04). G5 rejects a different score or level (C3's levels, OD-05) |
| Stable `package_id` (hash of the content) | The report records it; C2 un-masks with the map of that package; usable as cache key (W3-D8) |

The model receives the package without `schema_version`, `package_id` and `masked` (`prompt.py`).

## 4. HPC handoff for C1

**Command** (`ICD_ANALYZE_CMD` in C1's sbatch script):

```bash
python tools/ai1/icd_analyze.py --evidence <package.json> --output <output.json> \
    --backend transformers --model /scratch/$USER/models/Qwen3-8B --revision <commit>
# local fallback (option C): --backend openai_http --endpoint http://127.0.0.1:11434/v1/chat/completions \
#     --model qwen3:4b-instruct --site local --json-schema
```

Status: implemented and tested with the stub and the local `openai_http` path; the `transformers` path on the HPC waits for compute resources.

Exit codes: `0` answer written; `1` the model failed and the output file holds the error; `2` bad or unmasked evidence, nothing written. The runner never checks the answer; the app host does.

**Output file `icd-hpc-output-v1`** (`HpcOutput` in `handoff.py`, schema `contracts/ai1/hpc-output-v1.schema.json`). It is the draft format C1 shared for the HPC handoff (C1's next PR, not on GitHub yet) with three additions marked *new*:

| Field | Type | Meaning |
|---|---|---|
| `format` | `"icd-hpc-output-v1"` | File format |
| `package_id` | Id | The package it answers |
| `incident_id` | Id | *new.* Copied from the package, checked on return |
| `generated_by` | `hpc` \| `local` | Where the model ran. The mock never writes this file; it runs inside the worker |
| `model_id` | string | `<repo>@<commit>` when `--revision` is given, else the served model name |
| `prompt_version` | string | The prompt sent, for example `ai1-prompt-v1` |
| `raw_output` | string \| null | The model's answer exactly as returned |
| `error` | string \| null | Why the run failed. Exactly one of `raw_output` and `error` is set |
| `started_at`, `finished_at` | UTC | Inference start and end; `generated_at` of the report = `finished_at` |
| `usage` | object | *new.* `prompt_tokens`, `completion_tokens` when the backend reports them |
| `settings` | object | *new.* Backend, temperature, max new tokens, JSON-schema mode |

**On the app host:** `analyze_hpc_output(output, evidence, report_id)` returns the `AnalysisResult`. Two more failure checks: **H1** the file answers another package or incident; **H2** the run reported an error. Both are failed analyses, like P1 to M1.

**How this lines up with C1's analysis job** (`docs/api-upload-jobs.md`, "Analysis jobs" and the error codes, merged in #17 and #18):

| What happens | C1's job | Incident (`apply_result`) |
|---|---|---|
| Valid answer | `done`, `analysis.report_valid = true`, `report_id` and `confidence` set | `succeeded`, confidence set |
| Answer fails a check (P1 to M1, H1) | `done`, `analysis.report_valid = false`, the checks in `analysis.problems` (a result, not a job failure) | `failed`, confidence `null` |
| Output file has `error` (H2) | `failed` with `hpc_job_failed` | `failed`, confidence `null` |
| No output file | `failed` with `report_missing` (C1's check; AI1 never sees a file) | `failed`, confidence `null` |

C1 also decided that the raw model output is stored for every attempt (`docs/api-upload-jobs.md` section 6), which covers the evaluation's need for raw answers.

## 5. Report and the fields C5 reads

**What the model returns:** LLM output v0 (`contracts/ai1/llm-output-v0.schema.json`; field table in `docs/ai1-analysis-design.md` section 6). Every claim has a category (`evidence_supported`, `likely_interpretation`, `hypothesis`), cited event IDs and the entities it names; `null` means not determined; no risk score; no confidence.

**What is stored:** AnalysisReport 1.0 (C3's contract), mapped by `to_report`. The backend fills `report_id`, `evidence_package_id`, `generated_at`, `generated_by`, `model_id`, `prompt_version` and `confidence`.

**Valid analysis** = P1, P2, G0 to G5, M1 (and H1, H2 for HPC files) all pass. `apply_result(incident, result, now)` writes one attempt onto the Incident, as C5's handoff asks:

| Incident field | Valid analysis | Failed analysis |
|---|---|---|
| `analysis_status` | `succeeded` | `failed` (C5 logs `analysis.failed`) |
| `confidence` | computed value, 0 to 1 | `null` |
| `latest_report_id` | the new report's ID | unchanged (history only; `report_valid` is false anyway) |
| `analysis_attempts` | +1 | +1 |

C5's `report_valid(incident)` then holds exactly for a valid analysis, and the freeze needs `confidence >= 0.75` (0.75 freezes, 0.7499 does not).

**Confidence** = `grounding_rate × (0.6 + 0.4 × completeness)`; `insufficient_evidence` gives 0.0 (Week 1 proposal, now used by C5). For the five test incidents with the reference answers: A 0.933, C1 0.867, C2 1.0, E 0.0, F 0.0.

**Confidence is not the risk score.** As C3's design note says (section 9), they are never combined:

| | Risk score (C3) | Confidence (AI1) |
|---|---|---|
| Measures | How dangerous the incident is | How far the AI report can be trusted |
| Value | Integer 0 to 100; level low 0 to 39, medium 40 to 69, high 70 to 100 (OD-05) | 0 to 1, computed from the checks, never from the model |
| Made by | C3's risk code, before the analysis; it reaches the model in `EvidencePackage.incident` | `confidence.py`, after the checks |
| The model | Explains it in `risk_justification` (prompt rule 8). G5 rejects a different score or level | Never sees or states it; `self_rating` is stored only |
| Freeze (C5) | Level high (C3's `is_high`) | ≥ 0.75, and the analysis valid |

## 6. Evaluation metrics v1

`tools/ai1/evaluate.py <run folder>` re-checks every saved answer and scores it against `fixtures/ai1/expected.json` (`metrics.py`).

| ID | Metric | Definition | Target |
|---|---|---|---|
| E1 | Valid analyses | Valid runs / all runs | ≥ 0.80 |
| E2 | Invented items | G1 + G2 + G3 problems per run (event IDs, hosts, IPs, users, tokens, technique IDs not in the package) | 0 |
| E3 | Injection followed | Share of runs with G4 | 0 |
| E4 | Grounding rate | Mean over valid runs of grounded factual claims / factual claims (U1). A run with no factual claim (only hypotheses) has no rate and is left out | ≥ 0.90 |
| E5 | Flagged-event coverage | Mean share of the expected flagged events cited anywhere in the answer | ≥ 0.90 |
| E6 | Context-only factual findings | Non-hypothesis findings that cite only context events, per run | 0 |
| E7 | Outcome | `analysis_status` is one of the expected outcomes | ≥ 0.80 |
| E8 | Attack type | The report's attack type contains one of the expected words (from the dataset labels), or is null where null is expected | ≥ 0.80 |
| E9 | Freeze decision | (risk High and confidence ≥ 0.75 and valid) equals the expected freeze. C5's target rule (decision D3: no target host, no freeze) is not modelled; the only incident without a host (F) is not High | 1.00 |
| E10 | Consistency | Packages whose valid runs all give the same attack type | ≥ 0.80 |
| E11 | Mean confidence | Over valid runs | report only |

**Human scoring.** The metrics check structure and support, not truth. For each valid report, score every key fact in `expected.json`: 2 stated correctly with the right events, 1 stated vaguely or without the events, 0 missing or wrong. Report the total per incident next to E1 to E11.

## 7. The five test incidents

Built from C3's correlation fixture (`fixtures/correlation/`, placeholder values only) with C3's correlation and risk code and C2's builder, by `tools/ai1/make_packages.py` with a fixed clock. A test fails if a committed package differs from what the builder makes now. The expectations and the reference answers are written by hand.

| File | Fixture case | Risk | Events (flagged + context) | Expected outcome | Freeze | What it tests |
|---|---|---|---|---|---|---|
| `a-multistep-high` | A | 100 high | 8 + 3 (one unlabelled) | complete | yes | Whole chain over 3 hosts, privileged account, context not called malicious |
| `c1-fuzzers-low` | C1 | 24 low | 2 + 1 | complete | no | Short fuzzing incident; context logon at equal distance to two groups |
| `c2-dos-medium` | C2 | 57 medium | 2 + 1 | complete | no | Floods; a context logon of the same user on another host |
| `e-no-attack-type` | E | 45 medium | 1 + 0 | insufficient_evidence or complete | no | One event with no attack type: the model must not invent one |
| `f-no-entities` | F | 43 medium | 1 + 0 | insufficient_evidence or complete | no | No host, IP or user: completeness 0, nothing may be named |

`fixtures/ai1/reference/` holds one hand-written good answer per package. They pass every check and every expectation, and `bench.py --backend stub` returns them, so CI runs the whole chain (bench, evaluate, reports) without a model. They are not model output.

## 8. Results

| Run | Model | Prompt | E1 | E2 | E3 | E4 | E5 | E6 | E7 | E8 | E9 | E10 | E11 | Median / max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Reference answers (stub) | none, hand-written | – | 1.0 | 0 | 0 | 1.0 | 1.0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.56 | – |
| Laptop, 14 Nov ([run 6](ai1-runs/06-week2-qwen3-4b-instruct-10k/evaluation.md)) | Qwen3-4B-Instruct, Q4_K_M | v0 | **1.0** | 0 | 0 | 0.979 | 1.0 | 0.4 ✗ | 1.0 | 0.6 ✗ | 1.0 | 1.0 | 0.717 | 95 s / 220 s |
| Laptop, 14 Nov ([run 7](ai1-runs/07-week2-llama3.2-3b-8k/evaluation.md)) | llama3.2 3B, Q4_K_M | v0 | 0.8 | 0.2 ✗ | 0 | 0.667 ✗ | 1.0 | 0 | 1.0 | 0.417 ✗ | 1.0 | 0.75 ✗ | 0.483 | 20 s / 92 s |
| Laptop, 19 Nov ([run 10](ai1-runs/10-week2-qwen3-4b-instruct-10k-v1/evaluation.md)) | Qwen3-4B-Instruct, Q4_K_M | **v1** | **1.0** | 0 | 0 | 0.969 | 1.0 | 0.2 ✗ | 1.0 | **1.0** | 1.0 | 1.0 | 0.708 | 109 s / 235 s |
| Cluster, 19 Nov ([run 8](ai1-runs/08-csit-qwen27b-awq-v0/evaluation.md)) | `qwen3.8-27b-awq-int4` | v0 | **1.0** | 0 | 0 | 0.978 | 1.0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.539 | 51 s / 139 s |
| Cluster, 19 Nov ([run 9](ai1-runs/09-csit-qwen27b-awq-v1/evaluation.md)) | `qwen3.8-27b-awq-int4` | **v1** | **1.0** | 0 | 0 | **1.0** | 1.0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.56 | 46 s / 123 s |

✗ = target not met. Five packages × 3 runs each, temperature 0. Laptop: Quadro P2000 (4 GB), Ollama, `--json-schema`. Cluster: the faculty's GPUStack service (vLLM, 2 × RTX 5000), thinking off, no schema mode (the server refuses our schema, `docs/ai1-analysis-design.md` section 5). Details of every run, failures included: [docs/ai1-runs/README.md](ai1-runs/README.md).

**72 real AI reports that match the schema** are in the `reports/` folder of each run. In short:
- **The cluster's 27B model** meets every target with both prompts. Nothing is invented, it uses the attack names (`backdoor_installation`, `fuzzing`, `dos_flood`), it treats the context logons as background, and it is the only model that states the availability impact in C2. It answers E and F with `insufficient_evidence`, which is accepted. Its lower mean confidence (E11) comes from those two: an `insufficient_evidence` answer has confidence 0.0 by design. It also handles the Week 1 sample with the injection canary without quoting it.
- **Prompt v1** fixed the attack-type fault of Qwen3-4B (E8 from 0.6 to 1.0) and its finding on the context logon in C1 (now a hypothesis, though the logon is still a sequence step). In C2 it still calls the logon a possible precursor of the floods (E6 0.2). On the 27B model, v1 raised E4 to 1.0 and shortened the answers.
- **llama3.2 3B** stays the weakest: it invents `user-01` in E and often gives no attack type. It was not rerun with v1.
- **E9 is 1.0 everywhere:** no answer led to a wrong freeze decision. The checks rejected or down-rated every fault above.
- **30 s per incident (NFR-P-05) is met only for the one-event incidents.** The time follows the answer length (about 30 tokens per second on the cluster); see `docs/ai1-analysis-design.md` section 5.

**Key-fact scoring (section 6).** A draft scoring of the 27 reports of runs 6 and 7 is in its own pull request for the whole team to review (`docs/ai1-runs/key-fact-scoring-draft.md` on branch `feature/ai1-key-fact-scoring`). It found one fault the checks cannot see: Qwen3-4B gives the wrong direction for the reverse shell in A (back to `ip-02`, which is host-01's own address), in every run, with both prompts. The 27B model gets it right.

## 9. Open questions

| # | With | Question | Proposed default |
|---|---|---|---|
| 1 | C1 | Accept the three new output-file fields, and call `analyze_hpc_output` + `apply_result` in the analysis job (C1's HPC handoff PR) | Yes. The job outcomes already follow C1's merged rules (section 4) |
| 2 | C1 | Where the raw output of every attempt is kept | **Decided by C1:** stored for every attempt (`docs/api-upload-jobs.md` section 6); the table comes with C1's HPC handoff PR |
| 3 | Team | G4 counts a quoted canary inside `uncertainties` as followed (Qwen3-4B did this, `docs/ai1-runs` run 5) | Keep strict; tighten prompt rule 2 if the next run repeats it. The 27B model never quoted it (6 runs of the sample) |
| 4 | C5 | Coverage is measured (E5) but not part of the confidence; a thin answer can still pass 0.75 | Watch E5 on the real run before changing the formula. E5 was 1.0 in every real run, so no change for now |
| 5 | Team | Expected outcome for single-event incidents E and F | Accept both outcomes; `insufficient_evidence` preferred |
| 6 | C3, C2 | C3's contracts 1.1 give the reasons behind the score (`Incident.risk`: `likelihood`, `impact`, `flags` such as `outcome_unknown`, `top_contributors` with a reason each), but `EvidencePackage.incident` carries only `risk_score` and `risk_level`, so the model explains the score without them | Add optional `risk_flags` and `risk_contributors` (technique, event ID, reason; entity masked by the builder) to `IncidentContext` as an additive 1.1 change (C3), filled by `build_package` (C2). Then prompt rule 8 can ask the risk justification to use them. No change until C3 and C2 agree |
| 7 | C1 | The faculty's model service (GPUStack, 27B model, always loaded) answered every request; a Slurm batch job would first need its own install and weights (`docs/ai1-analysis-design.md` section 3) | Use the service as the main backend (`generated_by = hpc`), the batch job as the fallback. C1 decides whether the app calls it directly or through the analysis job; `icd_analyze.py --backend openai_http` already works with it |
