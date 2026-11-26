#!/usr/bin/env bash
# Slurm job: prepare the NetFlow v3 data and train the risk-v1 confidence classifier (CPU only).
# Runbook: docs/confidence-classifier.md. Edit the CHANGE_ME lines, then from the repo root:
#   sbatch tools/confidence/train_confidence.sbatch
# PBS: replace the #SBATCH lines with #PBS -l walltime=03:00:00,select=1:ncpus=16:mem=48gb
#SBATCH --job-name=icd-confidence
#SBATCH --partition=CHANGE_ME          # a CPU partition; no GPU is needed
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G                      # the arrays are a few GB; pyarrow batches are 64 MB
#SBATCH --time=03:00:00
#SBATCH --output=%x_%j.out
set -euo pipefail
DATA=${DATA:-/scratch/$USER/icd-data}          # holds the two NF-v3 CSVs (never in the repo)
RUN=${RUN:-/scratch/$USER/icd-confidence/${SLURM_JOB_ID:-local}}
MODEL=${MODEL:-hgb}                             # hgb (scikit-learn) or lightgbm
# module load python                            # if your site uses modules
# source ~/venvs/icd-confidence/bin/activate    # venv with tools/confidence/requirements.txt
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-16}
cd backend
python -m app.confidence.prepare --out "$RUN/prepared" \
  --input nf-unsw-nb15-v3="$DATA/NF-UNSW-NB15-v3.csv" \
  --input nf-cse-cic-ids2018-v3="$DATA/NF-CSE-CIC-IDS2018-v3.csv"
# 1. both datasets (the model risk-v1 uses), 2. and 3. cross-dataset checks (design 9A.2)
python -m app.confidence.train --prepared "$RUN/prepared" --out "$RUN/both" --model "$MODEL" \
  --threads "$OMP_NUM_THREADS"
python -m app.confidence.train --prepared "$RUN/prepared" --out "$RUN/unsw-only" --model "$MODEL" \
  --threads "$OMP_NUM_THREADS" --train-datasets nf-unsw-nb15-v3
python -m app.confidence.train --prepared "$RUN/prepared" --out "$RUN/cic-only" --model "$MODEL" \
  --threads "$OMP_NUM_THREADS" --train-datasets nf-cse-cic-ids2018-v3
echo "reports: $RUN/*/report.json (counts and measures only; safe to share)"
echo "never commit $RUN/prepared (real rows) or a model file without review"
