# LLM opinion per evidence group (risk-v1 step 5)

Owner: AI1 (the model and its runs), with C3 (risk) for the calibration. Design: [correlation-and-risk-design.md](correlation-and-risk-design.md) §9A.2, step 3. Decision: RV1-D15 in [decision-log.md](decision-log.md).

**Status: the code is built and tested on invented rows and a fake model server only. It has not been run on the real NetFlow v3 files or a real model yet, so no measure below is a result.** Nothing in the live risk score changes until step 6.

## 1. What it does

The risk score keeps one value per evidence group: the flagged events of one technique from one source-side entity (`correlation/risk.py`). For each group, the LLM is asked one short question: "do these flows show real `<technique>` activity by the source, rather than normal traffic?", answered yes or no. The answers become a raw value, and Platt scaling turns it into `p_llm`, a probability. In step 6, `p_llm` is stacked with the classifier's `p_clf` into the event confidence `C`.

The LLM never sees the label, never computes or changes the score, and never creates or removes a label (RV1-D2, RV1-D4). This is a separate prompt (`icd-group-opinion-v1`), not the AI report.

## 2. Choices

| What | Choice | Why |
|---|---|---|
| Datasets | NetFlow v3 events only (NF-UNSW-NB15-v3, NF-CSE-CIC-IDS2018-v3) | The same data as the classifier, so step 6 can stack the two on the same calibration blocks. Other datasets get no `p_llm` in risk-v1 yet (step 6 fallback) |
| What the model sees | A masked description of the group (`backend/app/confidence/groups.py`): the claimed technique, flow count, time span, number of destinations, top destination ports, protocols and applications, TCP flags seen, bytes and packets (totals and medians), share of flows with no reply or with retransmissions, TTL range, ICMP, DNS and FTP codes, and the first 10 flows one by one | Short (about 600 to 900 tokens), the same for training and run time, and enough to judge a technique |
| Masking | No IP, host or user: the source is `SRC`, destinations are `DST-1`, `DST-2`, ... in order of first appearance; times are seconds after the first flow | C2-D4: real entity values never leave the app host. Ports and flow statistics stay, because they are what is judged |
| Flows per group | The 50 earliest flows | Same cap as the evidence package (50 events) |
| Answer to number (`--mode`) | `samples` (default): 5 answers at temperature 0.7, raw = (yes + 0.5) / (valid + 1). `logprobs`: one answer at temperature 0 with the first token's top log-probabilities, raw = P(yes) / (P(yes) + P(no)) | Design 9A.2 names both. `samples` works on every OpenAI-compatible server (Ollama ignores `n`, so the client asks again until it has 5); `logprobs` is cheaper but needs vLLM or similar. The +0.5 / +1 keeps 5 of 5 below 1, so the logit stays finite |
| Failure | Fewer than 3 of 5 answers are yes or no, or the server fails after 2 retries: the group gets an error and no raw value | Never guessed; in step 6 the incident gets `llm_unavailable` (RV1-D3) |
| Calibration groups | Built from the calibration split of step 4 (same 1-hour blocks), never from the training blocks; the test groups from the test split | So the LLM is calibrated and checked on the same held-out blocks as the classifier |
| Positive groups | Attack flows of one (block, attack class, source IP); claim = that class; label 1. At most 150 per attack class (`--groups-per-class`) | Cap per class (9A.4), as in step 4 |
| Negative groups | Benign flows of one (block, source IP), given a claimed technique drawn at random (fixed seed) from the dataset's attack classes; label 0. As many as positive groups | Every group the score sees is flagged, so without negatives the LLM could only learn to say yes. A benign group with a wrong claim is the "label is wrong" case the confidence is about |
| Platt scaling | `p_llm = 1 / (1 + exp(-(a + b · logit(raw))))`, a logistic regression on the calibration groups (Platt 1999) | Design 9A.2. Two numbers, stored as plain JSON (no code runs when loaded) |
| Prior correction | The sample is about 1:1, the real share of attack groups is lower. `prior_shift = logit(natural share) - logit(sample share)` is stored and added to `a` at run time (Saerens et al. 2002) | So `p_llm` is not inflated by the balanced sample. The step 6 stacker refits its own intercept on events either way |
| Measures | On the test groups, per dataset and pooled: AUC, Brier score, ECE (15 bins) and reliability bins of the raw value and of `p_llm`, mean `p_llm` per true class, skipped and failed groups | Same measures as step 4. No pass mark is set for `p_llm` alone: the pass marks of 9A.2 apply to the final `C` in step 7 |

## 3. Code

| File | Purpose |
|---|---|
| `backend/app/confidence/groups.py` | Group description (`describe`), groups from stored events (`group_from_events`, used in step 6) and from a CSV split (`build_groups`, CLI `python -m app.confidence.groups`) |
| `backend/app/confidence/llm_opinion.py` | Prompt, answer parsing, OpenAI-compatible client (`samples` or `logprobs`), resumable runner (CLI `python -m app.confidence.llm_opinion`), `--backend stub` for dry runs |
| `backend/app/confidence/llm_calibrate.py` | Join, Platt fit, prior correction, report, `load()` that refuses another prompt, model or mode (CLI `python -m app.confidence.llm_calibrate`) |
| `backend/tests/confidence/test_llm_confidence.py` | 22 tests on invented rows and a fake server: masking, split, negatives, determinism, CSV and event paths giving the same flows, parsing, retries, resume, calibration end to end |
| `tools/confidence/llm_opinion.sbatch` | The HPC job (section 4) |

No new package: the HTTP client uses the standard library, and the fit uses scikit-learn (already added in step 4). Use the step 4 environment (`tools/confidence/requirements.txt`).

## 4. Running it

### 4.1 On HPC (Slurm)

1. The two CSVs and the step 4 virtual environment as in [confidence-classifier.md](confidence-classifier.md) §4.
2. A model server the job can reach, as `ICD_LLM_ENDPOINT` (for example `http://127.0.0.1:8000/v1/chat/completions`) and `ICD_LLM_MODEL` (the served name). `ICD_LLM_REVISION` records the weights commit; `ICD_LLM_API_KEY` is read if the server needs it and is never written to a file.
3. Edit the `CHANGE_ME` partition line and the `source` line in `tools/confidence/llm_opinion.sbatch`, then from the repo root: `sbatch tools/confidence/llm_opinion.sbatch`. Set `MODE=logprobs` when the server is vLLM and you want one request per group instead of five answers.
4. If the job hits its time limit, run it again: groups already answered with the same prompt, model and mode are kept and not asked again.

### 4.2 Groups on HPC, answers elsewhere

The groups files are masked, so they can be copied to a machine that reaches the model (for example the faculty model service through its SSH tunnel). From `backend/`:

```
python -m app.confidence.llm_opinion --groups groups-calibration.jsonl --out opinions-calibration.jsonl \
    --endpoint http://127.0.0.1:8000/v1/chat/completions --model <served name> --no-thinking
python -m app.confidence.llm_opinion --groups groups-test.jsonl --out opinions-test.jsonl \
    --endpoint http://127.0.0.1:8000/v1/chat/completions --model <served name> --no-thinking
python -m app.confidence.llm_calibrate --out run-llm \
    --calibration groups-calibration.jsonl opinions-calibration.jsonl \
    --test groups-test.jsonl opinions-test.jsonl
```

Keep `groups-*.manifest.json` next to each groups file: the calibrator reads the natural attack share from it.

### 4.3 Size and time (estimates, not measured on the real files)

- Groups: about 26 µs per CSV row per split on the development container, so about 10 minutes per split for the 22.5 M rows of both files.
- Opinions: at most 150 groups per attack class plus as many negatives, per dataset and split: a few thousand groups per split, each one request of about 600 to 900 prompt tokens and 5 one-word answers.

## 5. Output

| File | Content | Shareable |
|---|---|---|
| `groups-<split>.jsonl` | Per group: ID, dataset, split, true class, label `y`, masked description, its SHA-256 | Inside the team: masked, but derived from dataset rows |
| `groups-<split>.manifest.json` | Groups per class, chosen groups, natural attack share | Yes |
| `opinions-<split>.jsonl` | Per group: answer counts, raw value or error, prompt version, model, mode, samples, temperature | Yes |
| `llm_calibrator.json` | `a`, `b`, `prior_shift`, prompt version, model, mode, counts | Yes |
| `llm_report.json` | The measures of section 2 | Yes |

## 6. Limits

- Five samples give six possible raw values, so the calibrated `p_llm` has at most six levels per model; `logprobs` gives a continuous value.
- The negatives are benign traffic with a wrong claim. They do not cover an attack labelled with the wrong attack class; that case is not part of the label's confidence in risk-v1 (the technique comes from the dataset, RV1-D4).
- A group at run time is all flagged events of one technique and entity in an incident, which can span more than one hour; the calibration groups are one hour. The description uses at most 50 flows either way.
- The labels come from the dataset producers; agreement with them is not proof they are right (as in step 4).

## 7. Step 6a: combining p_clf and p_llm

`backend/app/confidence/stack.py` combines the two values into the event confidence `C` (design §9A.2 steps 4 to 6, decision RV1-D16), and `python -m app.confidence.stack_fit` fits it on the real groups:

```
python -m app.confidence.stack_fit --out run-stack \
    --model <step 4 run>/both/model.joblib --llm-calibrator run-llm/llm_calibrator.json \
    --calibration groups-calibration.jsonl opinions-calibration.jsonl \
    --test groups-test.jsonl opinions-test.jsonl \
    --input nf-unsw-nb15-v3=<path> --input nf-cse-cic-ids2018-v3=<path>
```

It reads the CSVs again for the 47 features of each group's flows, gives each flow its calibrated `p_clf` and its group's `p_llm`, fits the stacker on one half of the calibration groups and the conformal threshold on the other, and reports on the test groups: AUC, Brier score, ECE, conformal coverage (target 95%) and the share of events that would get `needs_review`. Output `stacker.json` (plain JSON) and `stack_report.json` (counts and measures only).

## 8. Step 6b: the confidence job on HPC

User decision of 26 Nov 2026: the models run as an HPC batch job, not in the app's worker (decision RV1-D17). With `ICD_CONFIDENCE_BACKEND=hpc_batch`, an upload of a NetFlow v3 dataset goes:

1. **Ingest job:** events stored, incidents correlated and scored as **phase 1** (`initial`): every flagged event keeps its dataset's fixed `C`, flags `confidence_fixed` and `llm_pending`. A confidence job is queued instead of the analysis jobs. An initial High score may already start a freeze, with `llm_pending` shown (user, 26 Nov 2026).
2. **Confidence job** (`backend/app/jobs/confidence.py`): writes the input file (`app/confidence/handoff.py`: the 47 features of each flagged NetFlow v3 event and the masked description of each evidence group; no IP, port, time, host, user or label), copies it to the cluster and submits `tools/confidence/icd_confidence.sbatch` over the same SSH and Slurm handoff as the AI report (`ICD_HPC_*`), then reads the output.
3. **Cluster** (`python -m app.confidence.batch_run`): `p_clf` from the step 4 model, `p_llm` from the step 5 prompt and Platt calibrator, `C` from the 6a stacker (with `needs_review`). A group whose LLM opinion fails gets `C` = `p_clf` with `llm_unavailable`. A failure of the whole run is written as an output with `error`.
4. **Back in the worker:** the incidents are scored again as **phase 2** (`final`). If the cluster gives no answer, the job is tried again (`JOB_MAX_ATTEMPTS`); after the last attempt, the incidents are scored again with `llm_unavailable` and the initial score stays current, never shown as final. Either way the analysis jobs are queued next, so the AI report runs after phase 2.

Every score is kept in `risk_assessments` (append-only), so both the initial and the final score stay on record with their versions.

Setup once on the cluster: a checkout of the reviewed `main`, the step 4 venv, and the reviewed `model.joblib`, `llm_calibrator.json` and `stacker.json` in one folder (`MODELS` in the sbatch file). The calibrator is refused unless the LLM's model ID is the one it was fitted with. In `.env`: `ICD_CONFIDENCE_BACKEND=hpc_batch`, `ICD_CONFIDENCE_SBATCH_SCRIPT=<path on the cluster>` and the `ICD_HPC_*` connection.

With the backend `off` (the default), and for every other dataset, nothing changes: the risk-v0 score, no confidence job.
