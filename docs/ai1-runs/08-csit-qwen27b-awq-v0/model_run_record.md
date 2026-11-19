# Model-run and performance record

- Date (UTC): 2026-11-19T00:15:57+00:00
- Host: DESKTOP-6VIN52L | CPUs: 12 | RAM: 33.7 GB | GPUs: ['Quadro P2000, 4096 MiB, 573.71']
- Scheduler job: none (interactive or local)
- Model: qwen3.8-27b-awq-int4 | revision: server-side: record it by hand | backend: openai_http | quantization: AWQ int4 (vLLM 0.33.0, tensor parallel 2)
- Licence: NOT CHECKED: weights source not visible to students; ask the cluster admin
- Prompt: ai1-prompt-v0 | temperature: 0.0 | output constrained to the JSON Schema: no
 | thinking: off

| Question | Answer |
| --- | --- |
| Did the model load? | yes |
| Load time | 0.31 s |
| Runs | 18 |
| Inference time (median / max) | 58.63 s / 139.46 s |
| Tokens per second (median) | 29.8 |
| Peak process RAM | 43 MB |
| Peak GPU memory used | 3971 MB |
| Valid analyses (parse + grounding + contract) | 18 of 18 |
| Attack types across valid runs | DoS, None, backdoor_installation, credential_brute_force_and_data_exfiltration, fuzzing |
| Flagged events cited by a step or finding (median) | 100% |
| Confidence of valid runs (min / max) | 0.0 / 1.0 |
| Inference within 30 s (NFR-P-05) | NOT met |

Failed checks across runs: none

The stub backend measures the harness only. For openai_http, --warmup times the model load (unload it on the server first). Fill the licence line from the model card before use.
