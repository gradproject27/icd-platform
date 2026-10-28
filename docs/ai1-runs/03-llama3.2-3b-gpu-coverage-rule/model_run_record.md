# Model-run and performance record

- Date (UTC): 2026-10-26T13:22:14+00:00
- Host: DESKTOP-6VIN52L | CPUs: 12 | RAM: 33.7 GB | GPUs: ['Quadro P2000, 4096 MiB, 573.71']
- Scheduler job: none (interactive or local)
- Model: llama3.2-3b-8k | revision: server-side: record it by hand | backend: openai_http | quantization: Q4_K_M
- Licence: Llama 3.2 Community Licence (from ollama show llama3.2:3b, 2026-10-26); not verified on the HF card; num_ctx 8192, num_gpu 99
- Prompt: ai1-prompt-v0 | temperature: 0.0 | output constrained to the JSON Schema: yes

| Question | Answer |
| --- | --- |
| Did the model load? | yes |
| Load time | 6.65 s |
| Runs | 3 |
| Inference time (median / max) | 124.04 s / 140.51 s |
| Tokens per second (median) | 15.9 |
| Peak server 'ollama' RAM | 174 MB |
| Peak GPU memory used | 2961 MB |
| Valid analyses (parse + grounding + contract) | 3 of 3 |
| Attack types across valid runs | brute_force |
| Flagged events cited by a step or finding (median) | 100% |
| Confidence of valid runs (min / max) | 0.8364 / 0.8457 |
| Inference within 30 s (NFR-P-05) | NOT met |

Failed checks across runs: none

The stub backend measures the harness only. For openai_http, --warmup times the model load (unload it on the server first). Fill the licence line from the model card before use.
