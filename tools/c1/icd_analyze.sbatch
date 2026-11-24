#!/usr/bin/env bash
# C1 HPC batch handoff (decision F4): the Slurm job the worker's hpc_batch backend submits.
# One masked evidence file in ($ICD_EVIDENCE), one icd-hpc-output-v1 file out ($ICD_OUTPUT).
# Written for the national HPC; NOT yet run there (no access). Copy it to the cluster, edit the
# CHANGE_ME lines, and set ICD_HPC_SBATCH_SCRIPT to its path (docs/prototype-architecture.md §5).
#SBATCH --partition=CHANGE_ME          # from tools/ai1/hpc_probe.sh check 2
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G                      # model size + 4 GB headroom
#SBATCH --time=00:30:00                # one incident; at most the partition's MaxTime
#SBATCH --output=%x_%j.out
set -euo pipefail
: "${ICD_EVIDENCE:?the worker sets ICD_EVIDENCE}"
: "${ICD_OUTPUT:?the worker sets ICD_OUTPUT}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
REPO=${ICD_REPO:-$HOME/icd-platform}                 # a checkout of this repo on the cluster
MODEL_DIR=${MODEL_DIR:-/scratch/$USER/models/CHANGE_ME}
REVISION=${REVISION:-CHANGE_ME_COMMIT_HASH}          # must match the worker's ICD_HPC_MODEL pin
# module load python cuda                            # if your site uses modules
# source ~/venvs/icd-ai1/bin/activate                # venv with tools/ai1/requirements-bench.txt
cd "$REPO"
# Exit code 1 (the model failed) still leaves an output file with "error" set; the worker reads
# it and reports hpc_job_failed, so the script does not turn it into a Slurm failure.
python3 tools/ai1/icd_analyze.py --evidence "$ICD_EVIDENCE" --output "$ICD_OUTPUT" \
  --backend transformers --model "$MODEL_DIR" --revision "$REVISION" --site hpc || [ $? -eq 1 ]
