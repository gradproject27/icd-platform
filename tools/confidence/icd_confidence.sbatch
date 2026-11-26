#!/usr/bin/env bash
# Slurm job the worker submits for the risk-v1 confidence step (ICD_CONFIDENCE_BACKEND=hpc_batch).
# One input file in (ICD_CONFIDENCE_INPUT), one output file out (ICD_CONFIDENCE_OUTPUT); both are
# set by the worker with --export. Runbook: docs/confidence-llm.md section 8. Edit the CHANGE_ME
# lines once, copy this file to the cluster and set ICD_CONFIDENCE_SBATCH_SCRIPT to its path.
#SBATCH --job-name=icd-confidence-run
#SBATCH --partition=CHANGE_ME
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=%x_%j.out
set -euo pipefail
: "${ICD_CONFIDENCE_INPUT:?set by the worker}" "${ICD_CONFIDENCE_OUTPUT:?set by the worker}"
REPO=${REPO:-$HOME/icd-platform}                         # a checkout of the reviewed main branch
MODELS=${MODELS:-/scratch/$USER/icd-models}              # reviewed outputs of steps 4 to 6a
export ICD_CONFIDENCE_MODEL=${ICD_CONFIDENCE_MODEL:-$MODELS/model.joblib}
export ICD_CONFIDENCE_LLM_CALIBRATOR=${ICD_CONFIDENCE_LLM_CALIBRATOR:-$MODELS/llm_calibrator.json}
export ICD_CONFIDENCE_STACKER=${ICD_CONFIDENCE_STACKER:-$MODELS/stacker.json}
export ICD_LLM_ENDPOINT=${ICD_LLM_ENDPOINT:-CHANGE_ME}   # the model server the job can reach
export ICD_LLM_MODEL=${ICD_LLM_MODEL:-CHANGE_ME}         # the served name the calibrator was fitted with
# module load python                                     # if your site uses modules
# source ~/venvs/icd-confidence/bin/activate             # venv with tools/confidence/requirements.txt
cd "$REPO/backend"
python -m app.confidence.batch_run --no-thinking
