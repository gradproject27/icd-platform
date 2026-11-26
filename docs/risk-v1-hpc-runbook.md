# risk-v1 on HPC: one runbook for all runs

Owner: C3 (risk score). Status: proposed 26 Nov 2026, decision RV1-D18. Not run on the real cluster yet.

This page replaces the three separate runbooks for the real-data runs of risk-v1 (the details stay in [confidence-classifier.md](confidence-classifier.md) and [confidence-llm.md](confidence-llm.md)). One Slurm job runs steps 4, 5, 6a and 7 in order and ends with the validation report. A second, small job is what the app submits for each upload (phase 2, [confidence-llm.md](confidence-llm.md) §8).

## 1. What you need once

| Item | Where | Notes |
|---|---|---|
| Checkout of the reviewed `main` | `$HOME/icd-platform` | `git clone`, then `git pull` before each run |
| The two NF-v3 CSVs | `/scratch/$USER/icd-data/NF-UNSW-NB15-v3.csv`, `NF-CSE-CIC-IDS2018-v3.csv` | Never in the repo |
| Python 3.12+ venv | `~/venvs/icd-confidence` | `pip install -r tools/confidence/requirements.txt`; no root needed. Offline cluster: `pip download ... -d wheels` elsewhere ([confidence-classifier.md](confidence-classifier.md) §4) |
| A model server the compute node can reach | `ICD_LLM_ENDPOINT`, `ICD_LLM_MODEL` | OpenAI-compatible, for example vLLM on the same GPU node. `ICD_LLM_REVISION` records the weights commit; `ICD_LLM_API_KEY` is read if needed, never written |

In `tools/confidence/risk_v1_pipeline.sbatch`, edit the `CHANGE_ME` partition line and uncomment the `source` line of the venv (and `module load` if your site uses modules).

## 2. The run

From the repo root on the login node:

```
export ICD_LLM_ENDPOINT=http://127.0.0.1:8000/v1/chat/completions ICD_LLM_MODEL=<served name>
RUN=/scratch/$USER/icd-risk-v1/run1 sbatch tools/confidence/risk_v1_pipeline.sbatch
```

| # | Step | Command | Output in `$RUN` |
|---|---|---|---|
| 4 | Prepare, then train three times (both datasets; UNSW only; CIC only) | `prepare`, `train` | `prepared/` (real rows), `clf/{both,unsw-only,cic-only}/report.json`, `clf/both/model.joblib` |
| 5 | Masked groups for both splits, LLM opinions, Platt calibration | `groups`, `llm_opinion`, `llm_calibrate` | `llm/groups-*.jsonl`, `llm/opinions-*.jsonl`, `llm/llm_calibrator.json`, `llm/llm_report.json` |
| 6a | Stacker and conformal threshold | `stack_fit` | `stack/stacker.json`, `stack/stack_report.json` |
| 7 | Validation report | `validate` | `validation/validation.md`, `validation/validation.json` |

- **Resume.** Each step is skipped when its output exists, and opinions already given are not asked again. If the job stops or hits its time limit, submit the same command with the same `RUN`. To redo a step, delete its output folder first.
- **No model server.** Without `ICD_LLM_ENDPOINT` and `ICD_LLM_MODEL`, the job stops after the groups and says so. The groups are masked, so they can also be answered from another machine ([confidence-llm.md](confidence-llm.md) §4.2), with the answers put in `$RUN/llm/` under the same names, and the job submitted again.
- **Exit code.** 0 only when every check passes; 1 when a check fails or is missing. The report is written either way.
- **Size.** 16 cores, 48 GB, 8 hours requested. Estimates from invented rows, not measured on the real files: prepare about 5 minutes, groups about 10 minutes per split, opinions a few thousand requests per split, `stack_fit` one more pass over the CSVs.

## 3. The validation report (step 7)

`python -m app.confidence.validate --run $RUN` reads only the report files of the run (counts and measures, never rows) and writes `validation.md` and `validation.json`:

| Check | Mark (design §9A.2) | From |
|---|---|---|
| Calibrated `p_clf` AUC and ECE, per dataset, in-dataset | AUC ≥ 0.95, ECE ≤ 0.05 | `clf/both/report.json` |
| Stacked `C` AUC and ECE, per dataset and pooled, on the test groups | AUC ≥ 0.95, ECE ≤ 0.05 | `stack/stack_report.json` |
| Conformal coverage on the test groups | 0.95 ± 0.02 | `stack/stack_report.json` |

Reported without a mark: Brier scores, the cross-dataset results (trained on one dataset, tested on the other), `p_llm` AUC / ECE / Brier, the test groups left out, and the share of events that would get `needs_review`. Overall is `pass`, `fail`, or `incomplete` when an input or a measure is missing (a missing input is never skipped silently).

Scope: this validates the event confidence `C` only. The validation plan of the whole risk score (R6) is still open (RV1-D7).

## 4. What may be shared

| Share | Do not share or commit |
|---|---|
| `validation/validation.md` and `.json`, every `report.json`, `llm_report.json`, `stack_report.json` (counts and measures only) | `prepared/`, `groups-*.jsonl`, `opinions-*.jsonl` (derived from real rows) |
| `llm_calibrator.json`, `stacker.json` (plain numbers) | `model.joblib` except through a reviewed change: a joblib file runs code when it is loaded |

## 5. After a passing run: turning on phase 2

1. Put the validation report in a PR for review (Sara, C3). Nothing below is done before that review.
2. Copy the reviewed `clf/both/model.joblib`, `llm/llm_calibrator.json` and `stack/stacker.json` into one folder on the cluster (`MODELS`, default `/scratch/$USER/icd-models`).
3. In `tools/confidence/icd_confidence.sbatch`, set the partition and `ICD_LLM_ENDPOINT` / `ICD_LLM_MODEL` to the same served model the calibrator was fitted with (any other model ID is refused).
4. In the app's `.env`: `ICD_CONFIDENCE_BACKEND=hpc_batch`, `ICD_CONFIDENCE_SBATCH_SCRIPT=<path of icd_confidence.sbatch on the cluster>` and the `ICD_HPC_*` connection. Then every NetFlow v3 upload gets its phase 2 score from the cluster ([confidence-llm.md](confidence-llm.md) §8).

With `ICD_CONFIDENCE_BACKEND=off` (the default) the app keeps the risk-v0 score.
