# Model-run and performance record

- Date (UTC): 2026-10-26T09:15:31+00:00
- Host: DESKTOP-6VIN52L | CPUs: 12 | RAM: 33.7 GB | GPUs: ['Quadro P2000, 4096 MiB, 573.71']
- Scheduler job: none (interactive or local)
- Model: llama3.2-3b-8k | revision: server-side: record it by hand | backend: openai_http | quantization: Q4_K_M
- Licence: Llama 3.2 Community Licence (from ollama show llama3.2:3b, 2026-10-26); not verified on the HF card; num_ctx 8192
- Prompt: ai1-prompt-v0 | temperature: 0.0 | output constrained to the JSON Schema: yes

| Question | Answer |
| --- | --- |
| Did the model load? | yes |
| Load time | 8.45 s |
| Runs | 3 |
| Inference time (median / max) | 130.3 s / 141.02 s |
| Tokens per second (median) | 7.0 |
| Peak server 'ollama' RAM | 173 MB |
| Peak GPU memory used | 2357 MB |
| Valid analyses (parse + grounding + contract) | 3 of 3 |
| Attack types across valid runs | brute_force |
| Inference within 30 s (NFR-P-05) | NOT met |

Failed checks across runs: none

The stub backend measures the harness only. For openai_http, --warmup times the model load (unload it on the server first). Fill the licence line from the model card before use.
