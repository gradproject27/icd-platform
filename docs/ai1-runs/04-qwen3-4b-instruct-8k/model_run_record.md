# Model-run and performance record

- Date (UTC): 2026-10-26T14:04:09+00:00
- Host: DESKTOP-6VIN52L | CPUs: 12 | RAM: 33.7 GB | GPUs: ['Quadro P2000, 4096 MiB, 573.71']
- Scheduler job: none (interactive or local)
- Model: qwen3-4b-instruct-8k | revision: server-side: record it by hand | backend: openai_http | quantization: Q4_K_M
- Licence: Apache-2.0 (from ollama show qwen3:4b-instruct = Qwen3-4B-Instruct-2507, 2026-10-26); verify on the HF card; num_ctx 8192, num_gpu 99
- Prompt: ai1-prompt-v0 | temperature: 0.0 | output constrained to the JSON Schema: yes

| Question | Answer |
| --- | --- |
| Did the model load? | yes |
| Load time | 5.68 s |
| Runs | 3 |
| Inference time (median / max) | 197.22 s / 237.59 s |
| Tokens per second (median) | 15.2 |
| Peak server 'ollama' RAM | 135 MB |
| Peak GPU memory used | 3681 MB |
| Valid analyses (parse + grounding + contract) | 0 of 3 |
| Attack types across valid runs | n/a |
| Flagged events cited by a step or finding (median) | n/a |
| Confidence of valid runs (min / max) | n/a |
| Inference within 30 s (NFR-P-05) | NOT met |

Failed checks across runs: P1 x3

The stub backend measures the harness only. For openai_http, --warmup times the model load (unload it on the server first). Fill the licence line from the model card before use.
