#!/usr/bin/env bash
# Slurm job: the whole risk-v1 confidence pipeline in one run (steps 4, 5, 6a and 7).
# Runbook: docs/risk-v1-hpc-runbook.md. Edit the CHANGE_ME lines, then from the repo root:
#   RUN=/scratch/$USER/icd-risk-v1/run1 sbatch tools/confidence/risk_v1_pipeline.sbatch
# Each step is skipped when its output already exists, so the same command with the same RUN
# picks up where a stopped or timed-out job ended. The LLM steps need an OpenAI-compatible
# model server the compute node can reach (ICD_LLM_ENDPOINT, ICD_LLM_MODEL); without it the job
# stops after the groups and says so.
#SBATCH --job-name=icd-risk-v1
#SBATCH --partition=CHANGE_ME
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=08:00:00
#SBATCH --output=%x_%j.out
set -euo pipefail
DATA=${DATA:-/scratch/$USER/icd-data}          # holds the two NF-v3 CSVs (never in the repo)
RUN=${RUN:?set RUN to a folder, for example /scratch/$USER/icd-risk-v1/run1}
MODEL=${MODEL:-hgb}                             # hgb (scikit-learn) or lightgbm
GROUPS_PER_CLASS=${GROUPS_PER_CLASS:-150}
MODE=${MODE:-samples}                           # samples (any server) or logprobs (vLLM)
# module load python                            # if your site uses modules
# source ~/venvs/icd-confidence/bin/activate    # venv with tools/confidence/requirements.txt
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-16}
INPUTS=(--input nf-unsw-nb15-v3="$DATA/NF-UNSW-NB15-v3.csv"
        --input nf-cse-cic-ids2018-v3="$DATA/NF-CSE-CIC-IDS2018-v3.csv")
step() { echo "[$(date -u +%H:%M:%S)] $*"; }
cd backend
mkdir -p "$RUN/clf" "$RUN/llm" "$RUN/stack"

# Step 4: data and classifier (both datasets, then the two cross-dataset checks)
if [ ! -f "$RUN/prepared/manifest.json" ]; then
  step "prepare"; python -m app.confidence.prepare --out "$RUN/prepared" "${INPUTS[@]}"
fi
for NAME in both unsw-only cic-only; do
  [ -f "$RUN/clf/$NAME/report.json" ] && { step "skip train $NAME"; continue; }
  case $NAME in
    both) ONLY=() ;;
    unsw-only) ONLY=(--train-datasets nf-unsw-nb15-v3) ;;
    cic-only) ONLY=(--train-datasets nf-cse-cic-ids2018-v3) ;;
  esac
  step "train $NAME"
  python -m app.confidence.train --prepared "$RUN/prepared" --out "$RUN/clf/$NAME" \
    --model "$MODEL" --threads "$OMP_NUM_THREADS" "${ONLY[@]}"
done

# Step 5: groups, LLM opinions, Platt calibration
for SPLIT in calibration test; do
  [ -f "$RUN/llm/groups-$SPLIT.jsonl" ] && continue
  step "groups $SPLIT"
  python -m app.confidence.groups --split "$SPLIT" --out "$RUN/llm/groups-$SPLIT.jsonl" \
    --groups-per-class "$GROUPS_PER_CLASS" "${INPUTS[@]}"
done
if [ -z "${ICD_LLM_ENDPOINT:-}" ] || [ -z "${ICD_LLM_MODEL:-}" ]; then
  step "stopped after the groups: set ICD_LLM_ENDPOINT and ICD_LLM_MODEL and submit again"
  exit 0
fi
for SPLIT in calibration test; do   # asks only the groups not yet answered
  step "opinions $SPLIT"
  python -m app.confidence.llm_opinion --groups "$RUN/llm/groups-$SPLIT.jsonl" \
    --out "$RUN/llm/opinions-$SPLIT.jsonl" --mode "$MODE" --no-thinking --workers 8
done
if [ ! -f "$RUN/llm/llm_report.json" ]; then
  step "llm_calibrate"
  python -m app.confidence.llm_calibrate --out "$RUN/llm" \
    --calibration "$RUN/llm/groups-calibration.jsonl" "$RUN/llm/opinions-calibration.jsonl" \
    --test "$RUN/llm/groups-test.jsonl" "$RUN/llm/opinions-test.jsonl"
fi

# Step 6a: stacker and conformal threshold
if [ ! -f "$RUN/stack/stack_report.json" ]; then
  step "stack_fit"
  python -m app.confidence.stack_fit --out "$RUN/stack" \
    --model "$RUN/clf/both/model.joblib" --llm-calibrator "$RUN/llm/llm_calibrator.json" \
    --calibration "$RUN/llm/groups-calibration.jsonl" "$RUN/llm/opinions-calibration.jsonl" \
    --test "$RUN/llm/groups-test.jsonl" "$RUN/llm/opinions-test.jsonl" "${INPUTS[@]}"
fi

# Step 7: validation report (always rebuilt; exit 1 when a check fails or is missing)
step "validate"
STATUS=0
python -m app.confidence.validate --run "$RUN" || STATUS=$?
echo "share: $RUN/validation/validation.md and the */report.json files (counts and measures only)"
echo "never commit $RUN/prepared, groups or opinions files (real rows) or a model file without review"
exit "$STATUS"
