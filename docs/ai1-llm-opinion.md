# LLM opinion for C3's event confidence (AI1, risk-v1)

| | |
|---|---|
| **Owner** | AI1 |
| **For** | C3 (Sara): the `p_llm` input of the stacked event confidence `C` ([correlation-and-risk-design.md](correlation-and-risk-design.md) §9A.2 step 3, decision RV1-D2) |
| **Status** | Built and tested with the stub model. **Not yet run on the real model, not yet calibrated on real data, not yet wired into scoring.** Decisions AI1-OP-D1 to D6 are proposed |
| **Code** | `backend/app/opinion/`, tests in `backend/tests/opinion/` |
| **Formats** | [contracts/ai1/llm-opinion-v1.schema.json](../contracts/ai1/llm-opinion-v1.schema.json), [contracts/ai1/opinion-calibrator-v1.schema.json](../contracts/ai1/opinion-calibrator-v1.schema.json) (AI1's own formats, not shared contracts) |

## 1. What it is, and what it is not

For each evidence group `(technique, entity)` of an incident, the model is asked one question: *is this group malicious?* The answers become a probability `p_raw`. A Platt calibrator turns it into `p_llm`, where 0.8 should mean "right about 8 times in 10". C3's stacker combines `p_llm` with the classifier's `p_clf` into `C`.

| | LLM opinion (`p_llm`, this document) | Report confidence (OD-16) |
|---|---|---|
| Question | Is this evidence group a real attack? | Is the written report backed by its evidence? |
| Input | One group, masked and label-blind | The finished AI report |
| Prompt | `ai1-opinion-v1`, short yes/no | `ai1-prompt-v2`, the full report |
| Runs | After the initial score, before the final score (RV1-D3) | After the final score |
| Feeds | C3's `C`, then the risk score | C5's 0.75 freeze gate |

The two are separate code, separate prompts and separate numbers. They are **never combined** (design note §9, §9A.1).

## 2. Flow

```
incident + events
  -> incident_groups      same keys as C3's risk code (technique = attack type or "unknown", entity = entity_of)
  -> build_view           masked with C2's masking, label-blind, behaviour only, up to 20 events
  -> build_messages       prompt ai1-opinion-v1, fenced like prompt v2
  -> client.ask           n answers (samples) or one answer with token probabilities (logprob)
  -> p_raw                share of "yes", or P(yes) at the answer token
  -> calibrator           Platt scaling, p_llm = sigmoid(a * logit(p_raw) + b)
  -> GroupOpinion         one per group, keyed (technique, entity)
```

## 3. The output C3 reads: `GroupOpinion` (`icd-llm-opinion-v1`)

| Field | Meaning |
|---|---|
| `incident_id`, `technique`, `entity` | The group key, identical to C3's risk group key. `entity` is the real value: the record stays on the app host; the model only saw a token |
| `status`, `failure` | `ok`, or `failed` with the reason (`backend_error`, `too_few_valid_answers`, `no_logprobs`, `logprob_answer_mismatch`) |
| `p_raw` | Uncalibrated probability, 0 to 1. Null when failed |
| `p_llm` | Calibrated probability, **the value the stacker reads**. Null when failed or when no calibrator was given |
| `calibrator_version` | Set exactly when `p_llm` is set |
| `method`, `samples_requested`, `samples_valid`, `yes_count`, `temperature` | How `p_raw` was obtained |
| `prompt_version`, `model_id`, `cache_key` | Versions for C3's audit record (§9A.3 "Audit") |
| `event_count`, `shown_event_ids`, `reasons` | What the model saw (event IDs are recorded here, never sent) and up to 5 short reasons it gave |

**Failure rule.** A failure is never turned into a number. When `status` is `failed`, C3 keeps the classifier-only score and sets `llm_unavailable` (RV1-D3). When `p_llm` is null because no calibrator exists yet, C3 must treat it the same way: an uncalibrated `p_raw` is for evaluation only.

## 4. Label-blind view (AI1-OP-D1)

The view never contains the label, label status, attack type, incident role, risk, or event IDs. If it did, the model would read "attack: DoS" and agree, and `p_llm` would copy the label instead of adding an independent opinion. The stacker would then learn nothing from it.

What the model sees per group:
- **Counts over every event:** `event_count`, `span_seconds`, `distinct_dst_ips`, `distinct_dst_ports`, and the top event types and protocols.
- **Up to 20 events, spread evenly with first and last included.** Each has `t` (seconds since the first event), `type`, `protocol`, masked `src` and `dst`, `dst_port` and `summary`.

Example (one UNSW-NB15 flow from `fixtures/ingest/unsw-nb15-sample.csv`):

```json
{"dst": "ip-02", "dst_port": 139, "protocol": "tcp", "src": "ip-01",
 "summary": "tcp flow, state FIN, 0.04 s, 528 B out, 304 B in", "t": 0.0, "type": "network_flow"}
```

Safeguards, each covered by a test:
- **Masking.** C2's `mask_events` does the masking, and `find_leaks` checks the finished view. A real IP, host or user value stops the build.
- **Forbidden keys.** A label key such as `label`, `attack_type`, `role` or `event_id` anywhere in the view stops the build.
- **Event types.** C2's event types come from activity fields, never the label. A test checks that no event type in C2's vocabulary contains an attack category name.
- **Summaries.** A summary that names the event's own attack type has the name replaced with `[label removed]`. The real parsers never write it, but C3's hand-written fixture does ("Generic attack seen on …").
- **Prompt injection.** Tag-like text and chat tokens are replaced, as in prompt v2, including the opinion's own `event_group` tag. The group sits between tags whose ID the event text cannot guess.

## 5. Method (AI1-OP-D2, AI1-OP-D3)

| | `samples` (default) | `logprob` |
|---|---|---|
| Calls | 5 answers at temperature 0.7 (one request with `n=5` on vLLM; repeated requests on servers that ignore `n`) | 1 answer at temperature 0, `logprobs` with top 10 |
| `p_raw` | yes / valid answers (0, 0.2, ..., 1) | P(yes) / (P(yes) + P(no)) at the answer token |
| Fails when | Fewer than 3 of 5 answers parse | The server gives no token probabilities, or they disagree with the written answer |
| Cost | 5 short answers per group | 1 short answer per group |
| Resolution | 6 values only | Continuous |

`samples` is the default because it works on every server. `logprob` is cheaper and gives a finer value, but needs the faculty's vLLM service to return `logprobs`. That has **not been checked yet**. When it is, compare the two on the same calibration set and keep the one with the better out-of-fold log loss.

## 6. Calibration (AI1-OP-D4, AI1-OP-D5)

**Which datasets (data plan rows 2, 3 and 5; RV1-D5, RV1-D10).** `p_llm` is stacked with the classifier's `p_clf`, so it is calibrated on the classifier's datasets: **NF-UNSW-NB15-v3** and **NF-CSE-CIC-IDS2018-v3**. `label-set` refuses everything else, with the reason:

| Dataset | Why it is refused |
|---|---|
| Original UNSW-NB15 CSVs | Data plan row 5: CSV demo and ingestion test, not used for training; RV1-D10 keeps them for the demo, correlation evaluation and ground truth |
| Precinct6 | Agreement check only, never an input (RV1-D5, CON-20) |
| OTRF | Events are unlabelled; OTRF is the ATT&CK technique ground truth |

`fixture` (C3's synthetic events) is accepted for dry runs and tests only.

**Labelled set.** `labelled_groups` builds groups from one file, never from merged datasets:
- flagged events grouped by (attack type, entity) are positives (truth 1);
- unflagged events grouped by entity are negatives (truth 0);
- runs are cut at gaps over 60 minutes, as in C2-D14;
- unlabelled events are never used.

**Split by file or day, never by random rows (RV1-D5).** `label-set` reads one whole file, or one time range of it with `--start` and `--end`. The split is written into every result row and into the report.

**Natural attack ratio (RV1-D5).** `natural_sample` keeps the split's own share of attack groups. NF-UNSW-NB15-v3 is about 5.4% attack flows and NF-CSE-CIC-IDS2018-v3 about 12.9%. A 50/50 set would teach the calibrator a much higher base rate than real traffic has, and `p_llm` would come out too high. Within each class, groups are taken evenly spaced in time (deterministic, no hashing). Because attacks are rare, enough attack groups means asking about many groups: `label-set` warns below 30 attack groups.

**Fit.**
- Platt scaling is fitted by Newton's method on the log loss, with Platt's smoothed targets and step halving.
- It's pure Python, since the backend has no numpy.
- A calibrator records the method, prompt version and model it was fitted for. `estimate` refuses to apply it to any other setup.

**Honest measures.**
- `calibrate` takes the results of both datasets and fits **one** calibrator on them pooled.
- It reports Brier, log loss, ECE (10 bins) and AUC, raw and calibrated, **per dataset, as a macro average and pooled** (RV1-D5), plus a reliability table.
- The calibrated values are **out-of-fold** over 5 contiguous time blocks within each dataset: no group is scored by a fit that saw it, and the folds are time ranges, not shuffled rows.
- The pass marks of §9A.2 (ECE ≤ 0.05, AUC ≥ 0.95) are for the stacked `C`, not for `p_llm` alone. The report shows them for reference only.

**Which split.** The calibration range must be one that the classifier's training never sees (§9A.2 step 2). C2 owns the splits; the files and day ranges are to be agreed with C2 and C3 (open point 2).

**Stacking note for C3.** Platt scaling is a one-input logistic regression on `logit(p_raw)`. The stacker in step 4 is a logistic regression on `logit(p_clf)` and `logit(p_llm)`. Because `logit(p_llm) = a · logit(p_raw) + b`, if both are fitted on the same calibration split without regularisation, the stacker absorbs the Platt step: feeding it `p_raw` or `p_llm` gives the same final `C`. The calibrated `p_llm` still matters on its own, for display, for the evaluation above and for any fallback.

## 7. Cache and re-use (AI1-OP-D6)

- Only the model's answer is cached: the counts, `p_raw` and the reasons.
- The key is the SHA-256 of the view text, prompt version, model pin, method, samples and temperature.
- The calibrator is applied after the cache, so re-calibrating or re-scoring never calls the model again (§9A.3, "Re-score").
- Failed answers are not cached.
- Two groups with identical behaviour share one cached answer. The view holds no IDs, so they look the same to the model.

## 8. How to run (from `backend/`)

```bash
# Model: the same server as the report (runbook section 2); stub when unset
export ICD_OPINION_BACKEND=openai_http
export ICD_LLM_ENDPOINT=http://127.0.0.1:8000/v1/chat/completions ICD_LLM_MODEL=qwen3.8-27b-awq-int4
export ICD_LLM_SITE=hpc ICD_LLM_NO_THINKING=1   # ICD_LLM_API_KEY from the cluster, never committed

# 1. Labelled sets and the model's answers, one per NF-v3 file, on the agreed calibration range
#    (the ranges below are placeholders; the dataset files are never committed)
python -m app.opinion.cli label-set nf-unsw-nb15-v3 ../data/NF-UNSW-NB15-v3.csv \
    --start <from> --end <to> --groups 600 --out ../opinion-cal/nf-unsw --cache-dir ../opinion-cache
python -m app.opinion.cli label-set nf-cse-cic-ids2018-v3 ../data/NF-CSE-CIC-IDS2018-v3.csv \
    --start <from> --end <to> --groups 300 --out ../opinion-cal/nf-cic --cache-dir ../opinion-cache

# 2. One calibrator on both; writes calibrator.json, calibration.md and calibration.json
python -m app.opinion.cli calibrate ../opinion-cal/nf-unsw/results.jsonl \
    ../opinion-cal/nf-cic/results.jsonl --out ../opinion-cal \
    --version cal-nf-v3-qwen27b-v1 --source "NF-v3 calibration ranges agreed with C2 and C3"

# 3. Opinions for incidents, calibrated
python -m app.opinion.cli incidents ../fixtures/correlation/events.json --out ../opinion-run \
    --now 2026-01-16T00:00:00+00:00 --calibrator ../opinion-cal/calibrator.json
```

Use `--method logprob` to try token probabilities. `results.jsonl` and `opinions.jsonl` hold real group keys (entities): keep them on the app host, like the masking maps. Commit only counts and measures (`calibration.md`).

## 9. Not done yet (next steps)

| # | What | Who |
|---|---|---|
| 1 | First real run: both NF-v3 calibration ranges on the cluster's 27B model, both methods (about 900 groups: run off-peak, as the cluster guide asks); record `calibration.md` under `docs/ai1-runs/` | AI1 |
| 2 | Agree the calibration split: NF-v3 files and day ranges never used to train the classifier | C2, C3, AI1 |
| 3 | Check that the vLLM service returns `logprobs` (decides AI1-OP-D2) | AI1 |
| 4 | Stacker, conformal flag, two-phase scoring, contracts 1.4 (`llm_pending`, `llm_unavailable`, `confidence_versions`) | C3 |
| 5 | Job stage `llm_confidence` between the initial score and the AI report, and storage of `GroupOpinion` with the risk audit record | C1, C3 |
| 6 | Cost: one request (5 samples, or 1 with logprob) per evidence group. Measure the time per group on the cluster, then size the calibration runs (rare attacks make the sets large) and the per-incident cost in the platform | AI1 |
| 7 | Whether extra flow features (packets, TTL, loss) help the view. Note: TTL values are a known dataset artefact in UNSW-NB15 and could act as a label shortcut, so they are left out of v1 | AI1, C2 |
