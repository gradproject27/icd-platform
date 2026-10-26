#!/usr/bin/env bash
# hpc_probe.sh - read-only feasibility probe for the ICD AI1 task.
# Run it twice and keep both reports:
#   1) on the login node:        bash hpc_probe.sh login
#   2) inside a compute job:
#        Slurm: srun --pty -t 00:10:00 --gres=gpu:1 bash hpc_probe.sh compute
#        PBS:   qsub -I -l walltime=00:10:00 -l select=1:ngpus=1   then   bash hpc_probe.sh compute
# It changes nothing, installs nothing and downloads nothing except two tiny HTTPS header requests (check 7).
# Output: hpc_probe_<label>_<host>.txt  -> paste the PASS/BLOCKER lines at the end into the feasibility note.
LABEL="${1:-unlabelled}"
OUT="hpc_probe_${LABEL}_$(hostname -s).txt"
exec > >(tee "$OUT") 2>&1
have() { command -v "$1" >/dev/null 2>&1; }
sec() { printf '\n== %s ==\n' "$*"; }
RES=()
res() { RES+=("$1|$2|$3"); }   # id|PASS/WARN/BLOCKER/UNKNOWN|detail

echo "ICD AI1 HPC probe  label=$LABEL  date=$(date -u +%FT%TZ)  user=$USER  host=$(hostname)"

sec "1 Access and allocation"
echo "whoami: $(id -un)  groups: $(id -Gn)"
if have sacctmgr; then sacctmgr -n -P show assoc user="$USER" format=account,partition,qos,maxwall 2>&1 | head -10; res 1 PASS "sacctmgr answered (check the account lines above)"
elif have qstat; then echo "PBS-style scheduler (no sacctmgr)"; res 1 WARN "PBS: ask the admin for the project code"
else res 1 UNKNOWN "no scheduler client found on this node"; fi

sec "2 Scheduler and queues"
SCHED=none
if have sinfo; then SCHED=slurm; sinfo -s 2>&1 | head -20; res 2 PASS "Slurm"
elif have qstat; then SCHED=pbs; qstat -Q 2>&1 | head -20; res 2 PASS "PBS/Torque"
elif have bqueues; then SCHED=lsf; bqueues 2>&1 | head -20; res 2 PASS "LSF"
else res 2 BLOCKER "no sinfo, qstat or bqueues: no batch scheduler visible from here"; fi

sec "3 Walltime limits"
if [ "$SCHED" = slurm ]; then
  scontrol show partition 2>/dev/null | grep -E "PartitionName|MaxTime|DefaultTime|MaxNodes|AllowAccounts|TRES" | head -40
  MAXT=$(scontrol show partition 2>/dev/null | grep -o 'MaxTime=[^ ]*' | sort -u | tr '\n' ' ')
  res 3 WARN "partition MaxTime values: ${MAXT:-unknown}. Pass if a partition allows >= 1 h"
elif [ "$SCHED" = pbs ]; then qstat -Qf 2>/dev/null | grep -E "Queue:|resources_max.walltime" | head -20; res 3 WARN "see resources_max.walltime above"
else res 3 UNKNOWN "unknown scheduler"; fi

sec "4 CPU and RAM"
echo "nproc: $(nproc)"; free -g 2>/dev/null | head -2
[ -n "$SLURM_JOB_ID" ] && { echo "Slurm job $SLURM_JOB_ID: CPUs=$SLURM_CPUS_ON_NODE MEM_PER_NODE=$SLURM_MEM_PER_NODE"; }
RAMG=$(free -g 2>/dev/null | awk '/Mem:/{print $2}')
res 4 WARN "RAM ${RAMG:-?} GB on this node (pass if model size + 4 GB fits in the job's memory request)"

sec "5 GPU"
if have nvidia-smi; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
  [ "$SCHED" = slurm ] && sinfo -o "%P %G %D" 2>/dev/null | grep -i gpu | head
  res 5 PASS "$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"
else
  echo "nvidia-smi not found on this node"
  [ "$SCHED" = slurm ] && { echo "GRES in cluster:"; sinfo -o "%P %G" 2>/dev/null | grep -i gpu | head; }
  [ "$LABEL" = login ] && res 5 WARN "no GPU on the login node (normal): run the probe inside a GPU job" || res 5 BLOCKER "no GPU visible inside the job: request one (--gres=gpu:1) or plan CPU/quantized"
fi

sec "6 Storage and quota"
for d in "$HOME" "${SCRATCH:-/nonexistent}" "${WORK:-/nonexistent}" /tmp; do [ -d "$d" ] && df -h "$d" | tail -1; done
have quota && quota -s 2>&1 | head -5
have lfs && lfs quota -h -u "$USER" "$HOME" 2>&1 | head -5
res 6 WARN "check free space >= 40 GB for weights + cache + outputs, and the scratch purge policy"

sec "7 Network from this node"
for u in https://huggingface.co https://pypi.org; do
  code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' -I "$u" 2>/dev/null)
  echo "$u -> HTTP ${code:-no-response}"
done
echo "proxy vars: http_proxy=${http_proxy:-} https_proxy=${https_proxy:-}"
getent hosts huggingface.co >/dev/null && echo "DNS: resolves" || echo "DNS: huggingface.co does not resolve"
if curl -s -o /dev/null -m 8 -I https://huggingface.co; then res 7 PASS "outbound HTTPS works from this node"
else res 7 WARN "no outbound HTTPS: copy weights and wheels in beforehand (HF_HUB_OFFLINE=1)"; fi

sec "8 Container runtime"
for c in apptainer singularity podman docker; do have "$c" && echo "$c: $($c --version 2>&1 | head -1)"; done
if have apptainer || have singularity; then res 8 PASS "Apptainer/Singularity present"
elif have module; then module avail 2>&1 | grep -i -E "apptainer|singularity" | head -3; res 8 WARN "no container binary on PATH; check 'module avail' lines above"
else res 8 WARN "no container runtime found: use a venv or conda from modules"; fi

sec "9 Python and CUDA stack"
for p in python3 python pip3 conda mamba; do have "$p" && echo "$p: $($p --version 2>&1 | head -1)"; done
python3 - <<'PY' 2>&1
import importlib
for m in ("torch","transformers","vllm","llama_cpp","jsonschema","psutil","huggingface_hub"):
    try:
        mod = importlib.import_module(m); print(f"{m}: {getattr(mod,'__version__','present')}")
    except Exception: print(f"{m}: missing")
PY
have module && module avail 2>&1 | grep -i -E "cuda|python|cudnn" | head -8
res 9 WARN "see versions above; Python >= 3.10 and a CUDA module that matches the driver are needed"

sec "10 Policy on services and ports (answer by hand)"
echo "Ask the HPC admin, in writing:"
echo " a) May a job run a model server for several hours? Longest allowed job?"
echo " b) May a compute node open a port, and can the platform host reach it (SSH tunnel)?"
echo " c) May job output contain the dataset's log data, and where may it be stored?"
echo " d) Is outbound HTTPS from compute nodes allowed, or only through a proxy?"
echo " e) Is pseudonymised (masked) security-log data allowed on the cluster (NFR-S-07)?"
echo " f) How do we copy model weights in (scp/rsync to which path), and what is the purge policy?"
res 10 UNKNOWN "needs the admin's written answer"

sec "SUMMARY (paste into the feasibility note)"
for r in "${RES[@]}"; do IFS='|' read -r i s d <<<"$r"; printf 'check %-2s %-8s %s\n' "$i" "$s" "$d"; done
echo "Report saved to $OUT"
