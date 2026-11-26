#!/usr/bin/env bash
# Slurm job: the LLM opinion per evidence group and its Platt calibration (risk-v1 step 5).
# Runbook: docs/confidence-llm.md. Edit the CHANGE_ME lines, then from the repo root:
#   sbatch tools/confidence/llm_opinion.sbatch
# Part 1 (groups) needs only CPU. Part 2 (opinions) needs an OpenAI-compatible model server the
# compute node can reach, given as ICD_LLM_ENDPOINT and ICD_LLM_MODEL (for example vLLM started
# on the same GPU node, or the faculty model service). Without it, only part 1 runs, and the
# masked groups files can be answered from wherever the server is reachable (runbook 4.2).
#SBATCH --job-name=icd-llm-opinion
#SBATCH --partition=CHANGE_ME
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G                      # pyarrow batches of 64 MB; at most 50 flows per group
#SBATCH --time=04:00:00
#SBATCH --output=%x_%j.out
set -euo pipefail
DATA=${DATA:-/scratch/$USER/icd-data}          # holds the two NF-v3 CSVs (never in the repo)
RUN=${RUN:-/scratch/$USER/icd-llm/${SLURM_JOB_ID:-local}}
GROUPS_PER_CLASS=${GROUPS_PER_CLASS:-150}
MODE=${MODE:-samples}                           # samples (any server) or logprobs (vLLM)
# module load python                            # if your site uses modules
# source ~/venvs/icd-confidence/bin/activate    # venv with tools/confidence/requirements.txt
cd backend
for SPLIT in calibration test; do
  python -m app.confidence.groups --split "$SPLIT" --out "$RUN/groups-$SPLIT.jsonl" \
    --groups-per-class "$GROUPS_PER_CLASS" \
    --input nf-unsw-nb15-v3="$DATA/NF-UNSW-NB15-v3.csv" \
    --input nf-cse-cic-ids2018-v3="$DATA/NF-CSE-CIC-IDS2018-v3.csv"
done
if [ -z "${ICD_LLM_ENDPOINT:-}" ] || [ -z "${ICD_LLM_MODEL:-}" ]; then
  echo "groups written to $RUN; set ICD_LLM_ENDPOINT and ICD_LLM_MODEL to run part 2"
  exit 0
fi
for SPLIT in calibration test; do   # re-running the job asks only the groups not yet answered
  python -m app.confidence.llm_opinion --groups "$RUN/groups-$SPLIT.jsonl" \
    --out "$RUN/opinions-$SPLIT.jsonl" --mode "$MODE" --no-thinking --workers 8
done
python -m app.confidence.llm_calibrate --out "$RUN/calibrated" \
  --calibration "$RUN/groups-calibration.jsonl" "$RUN/opinions-calibration.jsonl" \
  --test "$RUN/groups-test.jsonl" "$RUN/opinions-test.jsonl"
echo "share: $RUN/calibrated/llm_report.json and llm_calibrator.json (no row values)"
