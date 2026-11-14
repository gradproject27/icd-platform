# Model-run and performance record

- Date (UTC): 2026-11-14T13:56:18+00:00
- Host: DESKTOP-6VIN52L | CPUs: 12 | RAM: 33.7 GB | GPUs: ['Quadro P2000, 4096 MiB, 573.71']
- Scheduler job: none (interactive or local)
- Model: qwen3-4b-instruct-10k | revision: server-side: record it by hand | backend: openai_http | quantization: Q4_K_M
- Licence: Apache-2.0 (from ollama show qwen3:4b-instruct = Qwen3-4B-Instruct-2507); verify on the HF card; num_ctx 10240, num_gpu 99
- Prompt: ai1-prompt-v0 | temperature: 0.0 | output constrained to the JSON Schema: yes

| Question | Answer |
| --- | --- |
| Did the model load? | yes |
| Load time | 7.08 s |
| Runs | 15 |
| Inference time (median / max) | 94.98 s / 219.71 s |
| Tokens per second (median) | 16.1 |
| Peak server 'ollama' RAM | 4520 MB |
| Peak GPU memory used | 3971 MB |
| Valid analyses (parse + grounding + contract) | 15 of 15 |
| Attack types across valid runs | Backdoors, None, evidence_supported |
| Flagged events cited by a step or finding (median) | 100% |
| Confidence of valid runs (min / max) | 0.0 / 1.0 |
| Inference within 30 s (NFR-P-05) | NOT met |

Failed checks across runs: none

The stub backend measures the harness only. For openai_http, --warmup times the model load (unload it on the server first). Fill the licence line from the model card before use.
