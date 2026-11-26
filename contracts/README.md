# Shared contracts

Owner: **C3**. **Frozen at the M1 gate on 25 Nov 2026** at contracts **1.3** (`schema_version` stays `"1.0"`: 1.1 to 1.3 only added optional fields; decision M1-D1). Every field is documented in [docs/contracts-v1.md](../docs/contracts-v1.md).

The six contracts are Event, Incident, EvidencePackage, AnalysisReport, ResponseAction and AuditRecord.

## Where things live

| What | Where | Edited by hand |
|---|---|---|
| Pydantic v2 models (the source of truth) | `backend/app/contracts/` | yes |
| JSON Schemas, one per contract | `contracts/schemas/<name>.schema.json` | **no, generated** |
| One valid synthetic example per contract | `contracts/examples/<name>.example.json` | yes |
| AI1's own formats, not shared contracts: LLM output v0, HPC output file, expected incident (see [docs/ai1-report-schema.md](../docs/ai1-report-schema.md)); regenerate with `cd backend; python -m app.analysis.export` | `contracts/ai1/<name>.schema.json` | **no, generated** |
| Dataset label mapping to `EventLabel` (owner C2, T1-06; see [docs/dataset-profile.md](../docs/dataset-profile.md)) | `contracts/label-mapping.json` | yes, hand-written, not generated |

Names: `event`, `incident`, `evidence-package`, `analysis-report`, `response-action`, `audit-record`.

Python code imports the models from `app.contracts`. Other languages (for example C4's TypeScript) read the JSON Schemas. Nobody redefines the contracts.

## Regenerate the schemas

```powershell
cd backend
python -m app.contracts.export
```

The output is byte-identical on Windows and Linux. `backend/tests/contracts/test_schemas.py` fails when a committed schema differs from what the models generate.

## Change rule

After the freeze, any change to a contract:

1. goes through a PR reviewed by C3;
2. lists the affected contracts in the PR description;
3. regenerates the schemas (and updates the examples and `docs/contracts-v1.md`);
4. bumps `SCHEMA_VERSION` in `backend/app/contracts/common.py`, and the `schema_version` literal of each top-level model, if the change is not backward compatible;
5. gets a decision-log entry and a dated version note in `docs/contracts-v1.md` (1.4, 1.5, ...). A change that only adds optional fields with a default keeps `schema_version` `"1.0"`; any other change needs the team's agreement first, because every component reads these contracts.
