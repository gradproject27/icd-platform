#!/usr/bin/env bash
# Slurm job for the AI1 model benchmark. Edit the CHANGE_ME lines, then from the repo root:
#   sbatch tools/ai1/run_bench.sbatch
# PBS: replace the #SBATCH lines with #PBS -l walltime=01:00:00,select=1:ncpus=4:mem=32gb:ngpus=1
#SBATCH --job-name=icd-ai1-bench
#SBATCH --partition=CHANGE_ME          # from probe check 2
#SBATCH --gres=gpu:1                   # delete this line for a CPU-only test
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G                      # model size + 4 GB headroom
#SBATCH --time=01:00:00                # at most the partition's MaxTime (probe check 3)
#SBATCH --output=%x_%j.out
# Offline-safe: the pinned weights were copied to MODEL_DIR beforehand (probe check 7).
set -euo pipefail
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
MODEL_DIR=${MODEL_DIR:-/scratch/$USER/models/CHANGE_ME}
REVISION=${REVISION:-CHANGE_ME_COMMIT_HASH}
LICENCE=${LICENCE:-"CHANGE_ME: licence name, model card URL, date checked"}
# module load python cuda              # if your site uses modules
# source ~/venvs/icd-ai1/bin/activate  # venv with tools/ai1/requirements-bench.txt
nvidia-smi || true
python3 tools/ai1/bench.py --backend transformers --model "$MODEL_DIR" --revision "$REVISION" \
  --runs 3 --max-new-tokens 3000 --licence-note "$LICENCE" \
  --out "tools/ai1/runs/${SLURM_JOB_ID:-local}"
