# Model-run and performance record

- Date (UTC): 2026-10-26T08:50:29+00:00
- Host: DESKTOP-6VIN52L | CPUs: 12 | RAM: None GB | GPUs: ['Quadro P2000, 4096 MiB, 573.71']
- Scheduler job: none (interactive or local)
- Model: llama3.2-3b-8k | revision: server-side: record it by hand | backend: openai_http | quantization: none
- Licence: Llama 3.2 Community Licence (from ollama show llama3.2:3b, 2026-10-26); not verified on the HF card; Q4_K_M, num_ctx 8192
- Prompt: ai1-prompt-v0 | temperature: 0.0

| Question | Answer |
| --- | --- |
| Did the model load? | yes |
| Load time | 0.0 s |
| Runs | 3 |
| Inference time (median / max) | 103.23 s / 269.79 s |
| Tokens per second (median) | 7.4 |
| Peak process RAM | n/a (no psutil) |
| Peak GPU memory used | 2357 MB |
| Valid analyses (parse + grounding + contract) | 0 of 3 |
| Attack types across valid runs | n/a |
| Inference within 30 s (NFR-P-05) | NOT met |

Failed checks across runs: P2 x3

The stub backend measures the harness only. For openai_http, note the server start-up time by hand as the load time. Fill the licence line from the model card before use.
