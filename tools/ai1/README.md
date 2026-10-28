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

Local run on the fallback path (option C in the design note) with [Ollama](https://ollama.com/). Make a copy of the model with an 8k context that runs fully on the GPU, otherwise the prompt (about 5,000 tokens) is cut and Ollama may split the model between CPU and GPU:

```powershell
"FROM llama3.2:3b`nPARAMETER num_ctx 8192`nPARAMETER num_gpu 99" | Out-File -Encoding ascii Modelfile
ollama create llama3.2-3b-8k -f Modelfile
ollama stop llama3.2-3b-8k          # so --warmup measures a real load
python tools/ai1/bench.py --backend openai_http --endpoint http://127.0.0.1:11434/v1/chat/completions `
    --model llama3.2-3b-8k --site local --runs 3 --warmup --json-schema --server-process ollama `
    --quantization Q4_K_M --licence-note "<licence>, <card URL>, checked <date>" --out tools/ai1/runs/local-llama3.2-3b
```

| Option | What it does |
|---|---|
| `--warmup` | Times a 1-token request first, so the model load is recorded as the load time and kept out of the inference times |
| `--json-schema` | Sends the LLM output v0 JSON Schema as `response_format`, so the server constrains the answer to it. Without it, `llama3.2:3b` gave 0 of 3 valid analyses |
| `--server-process` | Records the RAM of the model server's processes instead of `bench.py`'s own |
| `--quantization` | Writes the quantization the server uses (for example `Q4_K_M`) into the record |

Use a model without a thinking mode for timing: `qwen3:4b` on Ollama is the Thinking-2507 build and spends the whole token budget thinking; use `qwen3:4b-instruct`.

`tools/ai1/runs/` is ignored by git. Copy the final record of a real run into `docs/ai1-runs/` by hand, after checking it holds no dataset records.
