# AI1 test incidents (Week 2)

Five evidence packages for testing the AI analysis, their hand-written expectations and hand-written reference answers. Definitions and metrics: [docs/ai1-report-schema.md](../../docs/ai1-report-schema.md), sections 6 and 7.

| Path | Content | Edited by hand |
|---|---|---|
| `packages/<name>.json` | Masked EvidencePackage 1.0, built from `fixtures/correlation/events.json` by `python tools/ai1/make_packages.py` | **no, generated** |
| `expected.json` | What a correct analysis of each package shows (`contracts/ai1/expected-incident-v1.schema.json`) | yes |
| `reference/<name>.json` | A good LLM output v0 for each package; passes every check. Not model output | yes |

Placeholder values only (the correlation fixture's invented hosts, users and documentation IPs), masked again by C2's builder. No dataset records.
