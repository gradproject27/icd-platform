# Shared contracts

Owner: **C3**. Version **1.0**, draft until frozen at the M1 gate. Every field is documented in [docs/contracts-v1.md](../docs/contracts-v1.md).

The six contracts are Event, Incident, EvidencePackage, AnalysisReport, ResponseAction and AuditRecord.

## Where things live

| What | Where | Edited by hand |
|---|---|---|
| Pydantic v2 models (the source of truth) | `backend/app/contracts/` | yes |
| JSON Schemas, one per contract | `contracts/schemas/<name>.schema.json` | **no, generated** |
| One valid synthetic example per contract | `contracts/examples/<name>.example.json` | yes |

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
4. bumps `SCHEMA_VERSION` in `backend/app/contracts/common.py`, and the `schema_version` literal of each top-level model, if the change is not backward compatible.
