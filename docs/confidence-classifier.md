# Confidence classifier (risk-v1 step 4)

Owner: C3 (risk), with AI1 for the HPC run. Design: [correlation-and-risk-design.md](correlation-and-risk-design.md) §9A.2, steps 1 and 2. Decision: RV1-D14 in [decision-log.md](decision-log.md).

**Status: the code is built and tested on invented rows only. It has not been run on the real NetFlow v3 files yet, so no measure below is a result.** Nothing in the live risk score changes until step 6.

## 1. What it does

For a flagged flow, the classifier gives `p_clf`: how likely the dataset's "attack" label is right, judged from the flow's statistics. Isotonic regression then calibrates it, so 0.8 means "an attack about 8 times in 10". In step 6 this becomes part of the event confidence `C` (with the LLM's opinion, step 5). It never creates, changes or removes a label (RV1-D4).

## 2. Data and features

| What | Choice | Why |
|---|---|---|
| Datasets | NF-UNSW-NB15-v3 and NF-CSE-CIC-IDS2018-v3 (RV1-D10) | Same 55-column NetFlow v3 layout, so one model reads both |
| Features | The 47 flow statistics (`backend/app/confidence/features.py`) | All columns except IPs, ports, start and end times, `Label` and `Attack`. IPs, ports and times describe one lab, so a model that used them would learn the lab rather than the attack, and would not carry over to other data |
| Target | `Label` (1 attack, 0 benign) | The label whose confidence is rated |
| Split | 1-hour blocks of flow start time, each block whole to train (6 in 10), calibration (2 in 10) or test (2 in 10) by a hash of (dataset, block) | Design 9A.4 says split by file, day or scenario, never by random rows. Each dataset is one file and UNSW-NB15 covers only a few days, so hour blocks are the closest unit that still puts several attack windows in every split. Neighbouring flows never cross splits |
| Training sample | At most 100,000 rows per attack class and 500,000 benign rows per dataset (`--train-cap`, `--benign-cap`) | Cap per class (9A.4), so UNSW `Generic` or CIC `DDoS` cannot dominate |
| Calibration and test sample | One uniform rate per dataset, at most 1,000,000 rows (`--eval-rows`) | Keeps each dataset's natural attack ratio (9A.4) |
| Bad rows | `Label` not 0 or 1, or no start time: skipped and counted in the manifest | Never guessed |

The sampling uses a fixed seed, so the same files give the same arrays (tested).

## 3. Model and measures

| Step | Default | Option |
|---|---|---|
| Model | scikit-learn `HistGradientBoostingClassifier` (gradient-boosted trees, early stopping) | `--model lightgbm` when LightGBM is installed |
| Calibration | `IsotonicRegression` on the calibration split | — |
| Report | Per dataset and macro average: AUC, Brier score, expected calibration error (15 bins) and the reliability bins, before and after calibration; mean confidence per attack class | `--train-datasets` gives the cross-dataset runs |

Pass marks (design 9A.2, proposal): ECE ≤ 0.05 and AUC ≥ 0.95 on held-out blocks of the datasets the model trained on. Cross-dataset results are reported without a pass mark.

## 4. Running it

### On HPC (Slurm)

1. Copy the two CSVs to the cluster, for example `/scratch/$USER/icd-data/NF-UNSW-NB15-v3.csv` and `NF-CSE-CIC-IDS2018-v3.csv` (never into the repo).
2. Make a virtual environment with Python 3.12 or newer: `python3 -m venv ~/venvs/icd-confidence && ~/venvs/icd-confidence/bin/pip install -r tools/confidence/requirements.txt`. No root access is needed. If the cluster has no internet, build the wheels elsewhere with `pip download -r tools/confidence/requirements.txt -d wheels` and install from that folder.
3. Edit the `CHANGE_ME` partition line and the `source` line in `tools/confidence/train_confidence.sbatch`, then from the repo root: `sbatch tools/confidence/train_confidence.sbatch`. It is CPU only: 16 cores, 48 GB, 3 hours requested.
4. It runs the prepare step once and three trainings: both datasets (the model risk-v1 will use), UNSW only, and CIC only (cross-dataset checks).
5. Share the three `report.json` files (counts and measures only). Do not share `prepared/` (real rows). Hand a `model.joblib` over only through a reviewed change, because a joblib file runs code when it is loaded.

Time, estimated from invented rows on a 4-core development container: about 12 µs per row for the two prepare passes, so about 5 minutes for the 22.5 M rows of both files; training on the capped sample takes minutes.

### On a laptop

From `backend/`, with `pip install -r requirements-dev.txt`:

```
python -m app.confidence.prepare --out ../runs/conf/prepared \
    --input nf-unsw-nb15-v3=D:/data/NF-UNSW-NB15-v3.csv \
    --input nf-cse-cic-ids2018-v3=D:/data/NF-CSE-CIC-IDS2018-v3.csv
python -m app.confidence.train --prepared ../runs/conf/prepared --out ../runs/conf/both
```

## 5. Output

| File | Content | Shareable |
|---|---|---|
| `prepared/{train,calibration,test}.npz` | Feature arrays, labels, dataset and class codes | No: real rows |
| `prepared/manifest.json` | Input names, sizes and SHA-256; counts per split and class before and after sampling; skipped rows; settings | Yes |
| `<run>/report.json` | The measures of section 3, the pass check, row counts, fit time, every version (Python, NumPy, scikit-learn, input hashes) | Yes |
| `<run>/model.joblib` | Model, calibrator, feature list, versions; `app.confidence.train.load()` refuses another format or feature set | Only through review |

## 6. Limits

- Only NetFlow v3 events can be scored. Events from the original UNSW-NB15 CSVs, OTRF and Precinct6 have other fields, so in step 6 they get a flagged fallback `C` instead of a classifier value.
- The labels themselves come from the dataset producers; a model that agrees with them is not proof that they are right. Step 7 checks calibration and agreement, not the truth of the labels.
- Conformal `needs_review` (9A.2 step 5) and stacking with the LLM (9A.2 step 4) need `p_llm` ([confidence-llm.md](confidence-llm.md), step 5 of the plan), so they come in step 6.
