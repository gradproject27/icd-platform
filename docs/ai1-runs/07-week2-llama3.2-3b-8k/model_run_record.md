# Model-run and performance record

- Date (UTC): 2026-11-14T14:20:31+00:00
- Host: DESKTOP-6VIN52L | CPUs: 12 | RAM: 33.7 GB | GPUs: ['Quadro P2000, 4096 MiB, 573.71']
- Scheduler job: none (interactive or local)
- Model: llama3.2-3b-8k | revision: server-side: record it by hand | backend: openai_http | quantization: Q4_K_M
- Licence: Llama 3.2 Community License (from ollama show llama3.2:3b); verify on the HF card; num_ctx 8192, num_gpu 99
- Prompt: ai1-prompt-v0 | temperature: 0.0 | output constrained to the JSON Schema: yes

| Question | Answer |
| --- | --- |
| Did the model load? | yes |
| Load time | 10.68 s |
| Runs | 15 |
| Inference time (median / max) | 20.38 s / 92.06 s |
| Tokens per second (median) | 17.6 |
| Peak server 'ollama' RAM | 209 MB |
| Peak GPU memory used | 2967 MB |
| Valid analyses (parse + grounding + contract) | 12 of 15 |
| Attack types across valid runs | Backdoors, None |
| Flagged events cited by a step or finding (median) | 50% |
| Confidence of valid runs (min / max) | 0.0 / 1.0 |
| Inference within 30 s (NFR-P-05) | NOT met |

Failed checks across runs: G2 x3

The stub backend measures the harness only. For openai_http, --warmup times the model load (unload it on the server first). Fill the licence line from the model card before use.
