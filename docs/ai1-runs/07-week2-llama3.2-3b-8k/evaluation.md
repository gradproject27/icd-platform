# AI1 evaluation: week2-llama3.2-3b-8k

- Model: llama3.2-3b-8k | backend: openai_http | prompt: ai1-prompt-v0
- Runs scored: 15 | expectations: fixtures/ai1/expected.json

| Metric | Name | Value | Target | Met |
|---|---|---|---|---|
| E1 | Valid analyses | 0.8 | >= 0.80 | yes |
| E2 | Invented items per run (G1-G3) | 0.2 | 0 | no |
| E3 | Injection followed (G4) per run | 0.0 | 0 | yes |
| E4 | Grounding rate (valid runs) | 0.667 | >= 0.90 | no |
| E5 | Flagged-event coverage | 1.0 | >= 0.90 | yes |
| E6 | Context-only factual findings per run | 0.0 | 0 | yes |
| E7 | Outcome matches the expected one | 1.0 | >= 0.80 | yes |
| E8 | Attack type matches the labels (valid runs) | 0.417 | >= 0.80 | no |
| E9 | Freeze decision matches the expected one | 1.0 | 1.00 | yes |
| E10 | Same attack type across runs of a package | 0.75 | >= 0.80 | no |
| E11 | Mean confidence (valid runs) | 0.483 | report only | n/a |

| Package | Run | Valid | Failed checks | Outcome | Attack type | Coverage | Grounding | Confidence | Freeze (as expected) |
|---|---|---|---|---|---|---|---|---|---|
| a-multistep-high | 1 | yes | - | complete | n/a | 1.0 | 1.0 | 0.9333 | yes (yes) |
| a-multistep-high | 2 | yes | - | complete | Backdoors | 1.0 | 1.0 | 0.9333 | yes (yes) |
| a-multistep-high | 3 | yes | - | complete | Backdoors | 1.0 | 1.0 | 0.9333 | yes (yes) |
| c1-fuzzers-low | 1 | yes | - | complete | n/a | 1.0 | 0.0 | 0.0 | no (yes) |
| c1-fuzzers-low | 2 | yes | - | complete | n/a | 1.0 | 0.0 | 0.0 | no (yes) |
| c1-fuzzers-low | 3 | yes | - | complete | n/a | 1.0 | 0.0 | 0.0 | no (yes) |
| c2-dos-medium | 1 | yes | - | complete | n/a | 1.0 | 1.0 | 1.0 | no (yes) |
| c2-dos-medium | 2 | yes | - | complete | n/a | 1.0 | 1.0 | 1.0 | no (yes) |
| c2-dos-medium | 3 | yes | - | complete | n/a | 1.0 | 1.0 | 1.0 | no (yes) |
| e-no-attack-type | 1 | no | G2 | insufficient_evidence | n/a | 1.0 | n/a | n/a | no (yes) |
| e-no-attack-type | 2 | no | G2 | complete | n/a | 1.0 | n/a | n/a | no (yes) |
| e-no-attack-type | 3 | no | G2 | complete | n/a | 1.0 | n/a | n/a | no (yes) |
| f-no-entities | 1 | yes | - | insufficient_evidence | n/a | 1.0 | n/a | 0.0 | no (yes) |
| f-no-entities | 2 | yes | - | insufficient_evidence | n/a | 1.0 | n/a | 0.0 | no (yes) |
| f-no-entities | 3 | yes | - | insufficient_evidence | n/a | 1.0 | n/a | 0.0 | no (yes) |

Automatic metrics check structure and support, not truth. Score the key facts in fixtures/ai1/expected.json by hand for each valid report (docs/ai1-report-schema.md, section 6).
