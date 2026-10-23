# Shared contracts

Owner: **C3**. Event, Incident, EvidencePackage, AnalysisReport, ResponseAction and AuditRecord are defined here as Pydantic models once C3 freezes them (M1 gate).

Rules:
- Any change to a contract needs a PR reviewed by C3, and the PR must list the affected contracts.
- Other components import contracts from here; they do not redefine them.
