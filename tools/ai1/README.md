# AI1 tools: HPC probe and model benchmark

Owner: AI1. Design and decisions: [docs/ai1-analysis-design.md](../../docs/ai1-analysis-design.md). The analysis code these tools call lives in `backend/app/analysis/`.

| File | Purpose |
|---|---|
| `hpc_probe.sh` | Read-only HPC feasibility probe (10 checks). Run `bash tools/ai1/hpc_probe.sh login` on the login node, then `bash tools/ai1/hpc_probe.sh compute` inside a short compute job. It installs and downloads nothing. |
| `bench.py` | Runs prompt v0 on evidence packages and writes `model_run_record.md` and `.json`. Backends: `stub`, `openai_http`, `transformers`. |
| `run_bench.sbatch` | Slurm job for `bench.py` with the pinned weights (edit the `CHANGE_ME` lines). |
| `requirements-bench.txt` | Packages for `bench.py` outside the api image. |
| `samples/evidence-inc-ai1-0001.json` | Synthetic, masked EvidencePackage 1.0: 11 flagged and 2 context events, one with a prompt-injection canary (`CANARY-7F3A`). |
| `samples/llm-output-good-inc-ai1-0001.json` | Hand-written good LLM output v0 for that package (not model output). |

Quick check from the repo root, with the backend venv active:

```powershell
python tools/ai1/bench.py --backend stub --runs 1 --out tools/ai1/runs/stub
```

`tools/ai1/runs/` is ignored by git. Copy the final record of a real run into `docs/ai1-runs/` by hand, after checking it holds no dataset records.
