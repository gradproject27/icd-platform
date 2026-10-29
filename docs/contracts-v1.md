# Shared data contracts v1

| | |
|---|---|
| Owner | C3 (Detection & Correlation) |
| Version | 1.0 (`SCHEMA_VERSION`) |
| Status | **Draft until frozen at M1.** Every contract is pending agreement (section 7) |
| Tasks | T1-07, and the contract side of T1-09 |
| Reviewers | C2 (Event, EvidencePackage), AI1 (EvidencePackage, AnalysisReport), C5 (ResponseAction, AuditRecord, Incident), C1 (Incident) |

## 1. Purpose and files

ICD's components exchange six data contracts: **Event**, **Incident**, **EvidencePackage**, **AnalysisReport**, **ResponseAction** and **AuditRecord**. This document describes every field, so each consuming team can check that the contract gives them what they need before the M1 freeze.

| What | Where |
|---|---|
| Pydantic v2 models (source of truth) | `backend/app/contracts/` (`common.py`, `event.py`, `incident.py`, `evidence.py`, `report.py`, `response.py`, `audit.py`) |
| JSON Schemas (generated, never edited by hand) | `contracts/schemas/<name>.schema.json` |
| One valid synthetic example per contract | `contracts/examples/<name>.example.json` |
| Tests | `backend/tests/contracts/` |

`<name>` is `event`, `incident`, `evidence-package`, `analysis-report`, `response-action` or `audit-record`.

Python code imports from `app.contracts`. Other languages read the JSON Schemas. To regenerate the schemas after changing a model:

```powershell
cd backend
python -m app.contracts.export
```

The output is identical on Windows and Linux. A test fails if a committed schema is out of date. The change rule after the freeze is in [contracts/README.md](../contracts/README.md).

## 2. Conventions

These rules apply to all six contracts.

1. **Strict and immutable.** Every model extends `_Contract` (`extra="forbid"`, `frozen=True`). Unknown fields are rejected, and an instance cannot be changed after it is built.
2. **Versioned.** Every top-level model has `schema_version: "1.0"`, which defaults to `"1.0"`.
3. **IDs.** Every ID is a string of 1 to 128 characters from `A-Z a-z 0-9 . _ : -`.
4. **Times.** Every timestamp must carry a timezone; a timestamp without one is rejected. Values are converted to UTC and serialized as UTC (for example `2026-03-14T09:12:05Z`).
5. **Missing values.** One rule applies everywhere:
   - A value that the source does not provide is `null`. Optional fields default to `null`, so they may be left out on input, and they are always written as `null` on output.
   - Empty strings never mean "missing". Optional strings have a minimum length of 1, so `""` is rejected.
   - Sentinels such as `-`, `N/A`, `0.0.0.0` or `-1` are converted to `null` by C2's normalizer before an Event is built. The contract does not try to guess them.
   - In an AnalysisReport section, `null` means "not determined" (FR-14).
6. **Enums** are string enums with snake_case values. Two value sets are copied exactly from other documents instead: the catalogue IDs `S1` to `S4`, and the audit event types, which contain dots (`action.simulated`).
7. **Free-form extras** are allowed in only three places: `Event.extra_fields`, `ResponseAction.parameters` and `AuditRecord.details`. Their values must be JSON scalars (string, number, boolean or `null`); nested objects and lists are rejected.
8. **Described.** Every field has a description, which also appears in the JSON Schema.

In the tables below, **Required** means the key must be present. "default" means the key may be left out and the default shown is used.

## 3. Contracts

### 3.1 Event

**Purpose.** One normalized security event (FR-02, FR-04, FR-05, FR-40, FR-41, OD-21, TD-12).
**Produced by** C2's parser and normalizer. **Consumed by** C3 (correlation, risk scoring) and C2 (evidence package construction).

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `schema_version` | `"1.0"` | default | n/a | |
| `event_id` | Id | yes | Record is rejected by C2, never an Event. Unique and stable across re-ingestion of the same record | FR-03 |
| `timestamp` | UTC datetime | yes | Record is rejected by C2. When the activity happened (event time) | FR-03, TD-12 |
| `ingested_at` | UTC datetime | yes | n/a. When the record was parsed (arrival) | TD-12 |
| `event_type` | string, min 1 | yes | `"unknown"`. Normalized type from C2's vocabulary (**proposed**: C2 publishes the list) | FR-04 |
| `label` | EventLabel | yes | `status = unlabelled` | OD-21, FR-41 |
| `host` | string, min 1 | no | `null`. The host the event was observed on or is about | FR-04 |
| `src_ip`, `dst_ip` | IPv4 or IPv6 address | no | `null`. Invalid addresses such as `999.1.1.1` are rejected | FR-04 |
| `src_port`, `dst_port` | integer 0 to 65535 | no | `null` | FR-04 |
| `protocol` | string, min 1 | no | `null` | FR-04 |
| `user` | string, min 1 | no | `null`. Account name as in the source | FR-04 |
| `privileged_user` | boolean | no | `null` = the data does not say. Feeds the "privileged accounts" risk factor only where the data supports it | OD-04 |
| `summary` | string, 1 to 500 | yes | n/a. Short human-readable description built by C2 | FR-04 |
| `provenance` | Provenance | yes | n/a | FR-05 |
| `extra_fields` | object of JSON scalars | no | `{}`. Source fields that were not mapped. Columns listed in CON-20 never go here | FR-02, CON-20 |

**EventLabel**

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `status` | `flagged` \| `unflagged` \| `unlabelled` | yes | A missing label is `unlabelled`; it is never inferred | OD-21 |
| `raw_value` | string, min 1 | no | `null` only when the record had no label. Otherwise the label exactly as in the dataset | OD-21 |
| `attack_type` | string, min 1 | no | `null`. The dataset's attack-type column, kept as an attribute | OD-21 |
| `origin` | `"dataset"` | default | n/a. The system never generates labels | FR-41 |

**Provenance**

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `dataset_id` | Id | yes | n/a | FR-05 |
| `source_file` | string, min 1 | yes | n/a | FR-05 |
| `record_ref` | string, min 1 | yes | n/a. Row number, line number or original record ID | FR-05 |
| `source_format` | string, min 1 | yes | n/a. For example `csv` | FR-05 |

**Validators.**
- `label.status == unlabelled` if and only if `label.raw_value` is `null`.

### 3.2 Incident

**Purpose.** A group of related events (FR-07, FR-08, FR-11, FR-18 to FR-20, FR-31, FR-42, OD-09, TD-11).
**Produced by** C3's correlation and risk scoring. C5's response workflow updates `status`, and the analysis job updates the analysis fields. **Consumed by** C4 (dashboard), C5 (lifecycle, scenario lookup) and C2 (evidence package construction). C1 stores it.

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `schema_version` | `"1.0"` | default | n/a | |
| `incident_id` | Id | yes | n/a | FR-07 |
| `status` | IncidentStatus | default `new` | n/a | FR-31, TD-11 |
| `incident_type` | string, min 1 | no | `null` = not classified yet. C3 classification, read by C5's scenario lookup | OD-20 |
| `created_at`, `updated_at` | UTC datetime | yes | n/a. `updated_at >= created_at` | FR-07 |
| `first_event_at`, `last_event_at` | UTC datetime | yes | n/a. `last_event_at >= first_event_at` | FR-11 |
| `events` | list of IncidentEventLink, min 1 | yes | n/a | FR-08 |
| `risk` | RiskAssessment | no | `null` = not scored yet | OD-04, FR-18 |
| `analysis_status` | AnalysisStatus | default `not_started` | n/a | OD-09 |
| `analysis_attempts` | integer ≥ 0 | default `0` | n/a | OD-09 |
| `latest_report_id` | Id | no | `null` until a report is valid | FR-42 |
| `confidence` | number 0 to 1 | no | Set exactly when `analysis_status == succeeded`: every analysed incident has a confidence, and no valid analysis means no confidence | OD-16, FR-42 |

**IncidentStatus** values, with the display names from the response workflow spec, section 2. `IncidentStatus.label` returns the display name.

| Value | Display name |
|---|---|
| `new` | New (replaces "Detected", TD-11; `detected` is rejected) |
| `under_analysis` | Under Analysis |
| `awaiting_human_decision` | Awaiting Human Decision |
| `response_in_progress` | Response in Progress |
| `escalated` | Escalated |
| `resolved` | Resolved |
| `closed` | Closed |

**AnalysisStatus**: `not_started`, `in_progress`, `succeeded`, `failed`. "Analysis failed" is a status, not a lifecycle state (OD-09).

**IncidentEventLink**

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `event_id` | Id | yes | n/a | FR-08 |
| `role` | `flagged` \| `context` | yes | n/a. A context event is an unflagged or unlabelled event attached because it shares an entity in the window. **It is never treated as malicious** | OD-02 |
| `link_keys` | list of `host` \| `ip_pair` \| `user` | yes | Empty only for the event that started the incident. Records which key linked the event, so the dashboard can show why events were grouped | NFR-SF-05 |
| `linked_at` | UTC datetime | yes | n/a | FR-08 |

**RiskAssessment** (deterministic, computed by C3 code, never by the LLM)

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `score` | integer 0 to 100 | yes | n/a. A percentage | FR-18 |
| `level` | `low` \| `medium` \| `high` | yes | n/a | OD-05, FR-20 |
| `factors` | list of RiskFactor, min 1 | yes | n/a | FR-19 |
| `config_version` | string, min 1 | yes | n/a. Version of the weights and thresholds file used | FR-20 |
| `computed_at` | UTC datetime | yes | n/a | OD-04 |
| `likelihood` | number 0 to 1 | no (1.1) | `null` = not given. Combined evidence strength `L` | Team, 29 Oct 2026 |
| `impact` | number 0 to 1 | no (1.1) | `null` = not given. Asset impact `I` (FIPS 199) | Team, 29 Oct 2026 |
| `flags` | list of `asset_unknown` \| `outcome_unknown` \| `severity_default` | no (1.1) | `[]` | Team, 29 Oct 2026 |
| `top_contributors` | list of RiskContributor, max 3 | no (1.1) | `[]` | Team, 29 Oct 2026 |

**RiskFactor**: `name` (string, min 1), `value` (number 0 to 1, the normalized factor), `weight` (number ≥ 0), `contribution` (number, the points the factor adds to the score), `reason` (string or `null`, the plain-language reason; added in 1.1).

**RiskContributor** (1.1): `technique` (attack type, `unknown` when missing), `entity` (source-side entity, or `none`), `strength` (0 to 1), `event_id` (the group's strongest flagged event), `reason` (string).

**Contracts 1.1 (29 Oct 2026, additive).** The fields marked 1.1 are optional with a default, so every 1.0 document stays valid and `schema_version` stays `"1.0"` (change rule 4 in `contracts/README.md`: bump only for a change that is not backward compatible). They carry the output of the risk method of 29 Oct 2026 (design note section 9).

**No validator ties `level` to `score`.** The thresholds are configurable (FR-20), so the contract cannot know them. C3's scoring code applies the thresholds from the configuration named in `config_version`. The weights, factors and thresholds themselves come from T1-08. The numbers in the example file are placeholders; the factors follow the risk v0 method (likelihood and impact).

**Validators.**
- `updated_at >= created_at` and `last_event_at >= first_event_at`.
- Event IDs in `events` are unique.
- At least one link has `role = flagged`: an incident is never built from context events only (**proposed**).
- At most one link has empty `link_keys`. This follows from the rule that only the event that started the incident has none.
- `confidence` is not `null` exactly when `analysis_status == succeeded` (FR-42 criteria 1 and 4).
- `latest_report_id` is required when `analysis_status == succeeded` (FR-42 criterion 4).

### 3.3 EvidencePackage

**Purpose.** What the AI receives for one incident (OD-03, NFR-S-07, FR-13).
**Produced by** C2. **Consumed by** the LLM adapter and AI1's prompts, and by the grounding check that compares a report against its package.

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `schema_version` | `"1.0"` | default | n/a | |
| `package_id` | Id | yes | n/a | FR-13 |
| `incident_id` | Id | yes | n/a | FR-13 |
| `created_at` | UTC datetime | yes | n/a | FR-13 |
| `incident` | IncidentContext | yes | n/a. Incident metadata | OD-03 |
| `events` | list of EvidenceEvent, 0 to 50 | yes | n/a. **Up to 50 events: all flagged events first (up to the cap), then sampled context events** | OD-03 |
| `total_event_count` | integer ≥ 0 | yes | n/a. Events in the incident before the cap | OD-03 |
| `truncated` | boolean | yes | n/a. `true` when events were left out because of the cap | OD-03 |
| `masked` | boolean | default `true` | n/a. Host, user and IP values are pseudonymised before any HPC call. Masked values are consistent tokens within one package (for example `host-01`), so the grounding check can still compare entities | NFR-S-07 |

**IncidentContext**

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `incident_type` | string, min 1 | no | `null` = not classified yet | OD-03 |
| `risk_score` | integer 0 to 100 | no | `null` = not scored | OD-03, FR-18 |
| `risk_level` | `low` \| `medium` \| `high` | no | `null` = not scored | OD-03 |
| `first_event_at`, `last_event_at` | UTC datetime | yes | n/a | OD-03 |
| `flagged_event_count`, `context_event_count`, `host_count` | integer ≥ 0 | yes | n/a | OD-03 |

**EvidenceEvent** (the citable view of one Event)

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `event_id` | Id | yes | n/a. The ID the AI cites | FR-13 |
| `timestamp` | UTC datetime | yes | n/a | FR-13 |
| `event_type` | string, min 1 | yes | n/a | FR-04 |
| `role` | `flagged` \| `context` | yes | n/a | OD-02 |
| `label_status` | `flagged` \| `unflagged` \| `unlabelled` | yes | n/a | OD-21 |
| `attack_type` | string, min 1 | no | `null` | OD-21 |
| `host`, `src_ip`, `dst_ip`, `user` | string, min 1 | no | `null`. Strings, not IP types, because they may be masked tokens | NFR-S-07 |
| `summary` | string, 1 to 500 | yes | n/a | FR-13 |
| `source` | string, min 1 | yes | n/a. The provenance source, for example the file name | FR-05 |

**Validators.**
- On each EvidenceEvent: `role == flagged` requires `label_status == flagged`, and `role == context` requires `unflagged` or `unlabelled`, so a context event is never presented to the AI as flagged.
- Event IDs are unique.
- `len(events) <= total_event_count`.
- `truncated` is `true` if and only if `len(events) < total_event_count`.
- All flagged events come before any context event (OD-03 order).
- More than 50 events are rejected.

**Method.** `citable_event_ids()` returns the set of event IDs a report may cite.

### 3.4 AnalysisReport

**Purpose.** The AI's structured result for one incident (FR-14, FR-15, FR-17, FR-19, FR-42, OD-09, OD-16). C3 defines the contract; AI1 decides the semantics and writes the LLM output schema that maps into it.
**Produced by** the analysis component through the `LLMAnalyzer` adapter (mock, HPC or local). **Consumed by** C4 (report view), C5 (the 0.75 confidence gate for the freeze) and C1 (storage).

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `schema_version` | `"1.0"` | default | n/a | |
| `report_id` | Id | yes | n/a | FR-14 |
| `incident_id` | Id | yes | n/a | FR-14 |
| `evidence_package_id` | Id | yes | n/a. The package it was produced from | FR-13 |
| `generated_at` | UTC datetime | yes | n/a. The mock copies the package's `created_at`, because it cannot read a clock | |
| `generated_by` | `mock` \| `hpc` \| `local` | yes | n/a | |
| `model_id` | string, min 1 | no | `null` for the mock. Pinned model name | |
| `prompt_version` | string, min 1 | no | `null` for the mock | |
| `summary` | string, min 1 | yes | n/a. Concise summary | FR-14 |
| `attack_type` | string, min 1 | no | `null` = not determined | FR-14 |
| `sequence` | list of SequenceStep, min 1 | no | `null` = not determined | FR-14 |
| `findings` | list of Finding | yes | `[]` when there is no evidence | FR-14, FR-15 |
| `weaknesses` | list of strings, min 1 | no | `null` = not determined. Only when the evidence supports it | FR-14 |
| `impact` | string, min 1 | no | `null` = not determined | FR-14 |
| `recommendations` | list of strings | yes | `[]` allowed. Free text for the analyst. **Never drives an action**: C5 picks scenarios by catalogue lookup | C-10 |
| `risk_justification` | string, min 1 | no | `null` = not determined. The LLM explains the deterministic score; it does not produce a score | FR-19 |
| `uncertainty` | string, min 1 | yes | n/a. The uncertainty and limitations section | FR-15 |
| `confidence` | number 0 to 1 | yes | n/a. Computed by the analysis component from grounding and evidence completeness, **not by the model**. The mock sets `0.0` | OD-16 |
| `model_self_rating` | number 0 to 1 | no | `null`. The model's own rating. Stored, **never used for the 0.75 gate** | OD-16 |

**SequenceStep**: `order` (integer ≥ 1), `description` (string, min 1), `cited_event_ids` (list of Id, min 1).

**Finding**: `statement` (string, min 1), `category` (`evidence_supported` \| `likely_interpretation` \| `hypothesis`, FR-15), `cited_event_ids` (list of Id).

**No risk score in the report.** The score is deterministic and lives only in `Incident.risk` (OD-04). FR-14's "risk score" section is satisfied by the dashboard showing `Incident.risk.score` next to `risk_justification`. An AnalysisReport with a `risk_score` field is rejected.

**Validators.**
- An `evidence_supported` finding cites at least one event (FR-15 criterion 1). The other two categories may cite none.
- `sequence` orders are 1, 2, 3, ... in list order, with no gaps.

**Grounding helper.** `uncited_event_ids(report, evidence)` in `backend/app/llm/adapter.py` returns the IDs cited by any finding **or sequence step** that are not in `evidence.citable_event_ids()`, sorted. An empty list means every citation exists in the package.

### 3.5 ResponseAction

**Purpose.** A proposed or simulated response action (FR-23, FR-27, FR-28, FR-44, FR-45, NFR-SF-01, NFR-SF-07, OD-20). Fields follow the response workflow spec, section 12. **Every action is simulated: `simulated` is always `true` and no real system is touched.**
**Produced by** C5's response engine and simulated executor. **Consumed by** C4 (decision screen, history, `SIMULATED` label) and C5 (audit).

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `schema_version` | `"1.0"` | default | n/a | |
| `action_id` | Id | yes | n/a | |
| `incident_id` | Id | yes | n/a | |
| `scenario_id` | `S1` \| `S2` \| `S3` \| `S4` | yes | n/a. Catalogue v0. Anything else (for example `S5`) is rejected | OD-20, FR-44 |
| `state` | ActionState | yes | n/a | Spec §12 |
| `trigger` | `analyst_decision` \| `window_expiry` | no | `null` while proposed: when the recommended scenario is proposed at freeze start, nobody knows yet whether an analyst or the expiry will decide it. Required in every other state | FR-27 |
| `decided_by` | string, min 1 | no | `null` while proposed. A user ID or the literal `system` | FR-28 |
| `window_id` | Id | no | `null`. The response window, if the action came from a freeze | FR-43 |
| `target` | ActionTarget | yes | n/a | Spec §9 |
| `parameters` | object of JSON scalars | no | `{}` | Spec §9 |
| `proposed_at` | UTC datetime | yes | n/a | Spec §12 |
| `decided_at` | UTC datetime | no | `null` while proposed | Spec §12 |
| `executed_at` | UTC datetime | no | `null` until simulated | Spec §12 |
| `failure_reason` | string, min 1 | no | `null` unless the simulation failed | FR-45 |
| `comment` | string, min 1 | no | `null`. Optional analyst comment | FR-28 |
| `simulated` | `true` | default `true` | n/a. `false` is rejected | NFR-SF-01, NFR-SF-07 |

**ActionState**: `proposed`, `approved`, `simulated_succeeded`, `simulated_failed`. Spec section 12 writes the last two with hyphens (`simulated-succeeded`); the contract uses snake_case like every other enum (**proposed**, see section 9).

**ActionTarget**: `host`, `ip`, `account`, each a string (min 1) or `null`.

| Scenario (spec §9) | Simulated behaviour | Target required |
|---|---|---|
| S1 | Keep or apply host isolation, flag for investigation | `host` |
| S2 | Isolate host and block source IP | `host`, `ip` |
| S3 | Isolate host and disable account | `host`, `account` |
| S4 | Release isolation and raise monitoring | `host` |

**Validators.**
- `target.host` is required for every scenario; S2 also requires `target.ip`; S3 also requires `target.account`.
- `trigger == window_expiry` requires `decided_by == "system"`.
- `state == proposed` requires `trigger`, `decided_by` and `decided_at` to be `null`; every other state requires all three.
- `simulated_succeeded` and `simulated_failed` require `executed_at`.
- `simulated_failed` requires `failure_reason`; every other state requires `failure_reason` to be `null`.
- `proposed_at <= decided_at <= executed_at`, for the timestamps that are present.

**Not a shared contract: the response-window record.** Spec section 12 also lists a response-window record (window ID, incident ID, `started_at`, `deadline_at`, status `open`/`decided`/`expired`, recommended scenario ID). It is C5's own table, written and read only by the response workflow, so it is not defined here. ResponseAction refers to it through `window_id`.

### 3.6 AuditRecord

**Purpose.** A record of a security-relevant decision or action (FR-35, C-14, NFR-S-04, NFR-SF-07). The application only inserts audit records, never updates or deletes them; the model is immutable to match.
**Produced by** C5 (workflow, authentication) and C3 (`incident.*`). **Consumed by** C4 (audit view) and reviewers.

| Field | Type | Required | Missing value | Source |
|---|---|---|---|---|
| `schema_version` | `"1.0"` | default | n/a | |
| `record_id` | Id | yes | n/a | FR-35 |
| `occurred_at` | UTC datetime | yes | n/a. Database time (`now()`) when written | FR-35 |
| `event_type` | AuditEventType | yes | n/a | Spec §11, auth doc |
| `actor` | string, min 1 | yes | n/a. A user ID, the literal `system`, or `anonymous` for a failed login with no known user | FR-35 |
| `actor_role` | UserRole | no | `null` for `system` and `anonymous` | D7.1 |
| `incident_id` | Id | no | `null` for records with no incident (login, logout, lockout, access refused) | FR-35 |
| `result` | `success` \| `failure` \| `refused` \| `ignored` | yes | n/a | FR-35 |
| `simulated` | boolean | default `false` | n/a | NFR-SF-07 |
| `details` | object of JSON scalars | no | `{}`. For example previous and new state, scenario ID, window ID, reason. **Never passwords, hashes or session tokens** | C-14 |

**UserRole**: `soc_analyst`, `soc_manager`, `security_engineer`, `system_administrator` (D7.1).

**AuditEventType** (copied exactly; 21 values):

| Value | Incident-scoped | `simulated` | Source |
|---|---|---|---|
| `status_changed` | yes | false | Spec §11 |
| `transition_refused` | yes | false | Spec §11 |
| `analysis.failed` | yes | false | Spec §11 (proposed there) |
| `response_window.opened` | yes | false | Spec §11 |
| `response_window.reminder` | yes | false | Spec §11 |
| `decision.recorded` | yes | false | Spec §11 |
| `decision.refused` | yes | false | Spec §11 |
| `response_window.expired` | yes | false | Spec §11 |
| `expiry_duplicate_ignored` | yes | false | Spec §11 |
| `scenario.selected` | yes | false | Spec §11 |
| `scenario.no_match` | yes | false | Spec §11 |
| `action.simulated` | yes | **true** | Spec §11 |
| `isolation.released` | yes | **true** | Spec §11 |
| `notification.sent` | no | false | Spec §11 |
| `auth.login_succeeded` | no | false | Auth doc |
| `auth.login_failed` | no | false | Auth doc |
| `auth.logout` | no | false | Auth doc |
| `auth.lockout` | no | false | Auth doc |
| `access.refused` | no | false | Auth doc |
| `incident.created` | yes | false | **Proposed** by C3 (FR-07) |
| `incident.updated` | yes | false | **Proposed** by C3 (FR-09) |

**Difference from spec section 11.** Spec section 11 says every audit record has an incident ID. The authentication records from the auth doc (`auth.*`, `access.refused`) are the exception: a login or logout has no incident, so `incident_id` is `null` for them. `notification.sent` is not incident-scoped in this contract, because a notification may not concern a single incident. C5 can make it incident-scoped if every notification has one.

**Validators.**
- `action.simulated` and `isolation.released` require `simulated = true` (NFR-SF-07). Every other type requires `simulated = false`.
- Incident-scoped types (table above) require `incident_id`.
- `actor` of `system` or `anonymous` requires `actor_role` to be `null`; any other actor requires `actor_role`.

## 4. Example story

The six files in `contracts/examples/` tell one synthetic story, and a test checks that the cross-references match:

- **Events.** Brute-force SSH from `203.0.113.7` against internal host `ws-17` (`10.0.0.17`), user `svc-backup`. Three flagged events (`evt-0001` to `evt-0003`: two batches of failed logins, then a successful login) and one context event (`evt-0004`, an unflagged outbound connection). The Event example is `evt-0001`.
- **Incident** `inc-2026-0001`: risk score 74, level `high`, analysis succeeded with confidence 0.82, status `resolved` after the simulated response.
- **EvidencePackage** `pkg-2026-0001`: the four events, masked as `host-01`, `ip-01`, `ip-02`, `ip-03` and `user-01`.
- **AnalysisReport** `rpt-2026-0001`: two findings (one `evidence_supported`, one `hypothesis` with no citation) and a two-step sequence. Every cited ID is in the package.
- **ResponseAction** `act-2026-0001`: S2 (isolate `ws-17`, block `203.0.113.7`), `simulated_succeeded`, triggered by `window_expiry`, `decided_by = system`.
- **AuditRecord** `aud-2026-0001`: `action.simulated` by `system`, `simulated = true`.

Values the decisions do not give yet are placeholders in the examples: `event_type` names, `incident_type = brute_force`, the risk factors and `config_version`, and `model_id` / `prompt_version`.

## 5. Decisions applied

| Source | How the contracts apply it |
|---|---|
| OD-02 | Context events are attached by a shared entity in the window, have `role = context` and are never treated as malicious |
| OD-03 | EvidencePackage holds incident metadata and at most 50 events, flagged first, then sampled context; `total_event_count` and `truncated` say what was cut |
| OD-04 | The risk score is deterministic C3 code (`Incident.risk`); `privileged_user` is `null` when the data does not say |
| OD-05 | `RiskAssessment.level` is low, medium or high |
| OD-09 | Analysis failure is `analysis_status = failed`, not a lifecycle state |
| OD-16 | `AnalysisReport.confidence` is computed from grounding and completeness; `model_self_rating` is stored but never used for the 0.75 gate |
| OD-20 | `scenario_id` is restricted to catalogue v0, S1 to S4 |
| OD-21 | `EventLabel` keeps the raw dataset label and attack type; a missing label is `unlabelled` |
| NFR-S-07 | EvidencePackage entity fields are strings so they can carry masked tokens; `masked` defaults to `true` |
| NFR-SF-01, NFR-SF-07 | `ResponseAction.simulated` is always `true`; `action.simulated` and `isolation.released` audit records have `simulated = true` |
| NFR-SF-05 | `IncidentEventLink.link_keys` records why each event was grouped |
| TD-11 | Lifecycle state `new` replaces "Detected" |
| TD-12 | `Event.timestamp` (event time) and `Event.ingested_at` (arrival) are separate |
| FR-03 | Records without an ID or timestamp are rejected by C2 and never become Events |
| FR-05 | Every Event has a Provenance |
| FR-14, FR-15 | AnalysisReport sections, finding categories, the uncertainty section; `null` means "not determined" |
| FR-18, FR-19, FR-20 | Score 0 to 100 with a factor breakdown and the config version; no validator ties level to score |
| FR-31 | The seven lifecycle states |
| FR-41 | `EventLabel.origin` is always `dataset` |
| FR-42 | `confidence` is set exactly when analysis succeeded; `succeeded` requires `latest_report_id` |
| FR-44 | Any scenario outside the catalogue is rejected |
| C-10 | `recommendations` is free text and never drives an action |
| C-14, FR-35 | AuditRecord is immutable; `details` never carries secrets |

## 6. Changes from the provisional models

The provisional models in `backend/app/llm/contracts.py` are deleted. The adapter, the mock and their tests now import from `app.contracts`. No provisional field was removed.

| Old (provisional) | New | Reason |
|---|---|---|
| `_Strict` base (`extra="forbid"`) | `_Contract` (`extra="forbid"`, `frozen=True`) | Contracts are immutable |
| `str` IDs | `Id` (1 to 128 characters, restricted set) | One ID rule for all contracts |
| `datetime` (timezone optional) | UTC datetime, timezone required | A timestamp without a timezone is ambiguous |
| `EvidenceEvent.event_id`, `timestamp`, `source`, `summary` | Same names; `summary` limited to 500 characters | |
| (none) | `EvidenceEvent.event_type`, `role`, `label_status`, `attack_type`, `host`, `src_ip`, `dst_ip`, `user` | OD-03; entities are needed for the grounding check |
| `EvidencePackage.incident_id`, `events` | Same names; `events` capped at 50, flagged first | OD-03 |
| (none) | `EvidencePackage.package_id`, `created_at`, `incident`, `total_event_count`, `truncated`, `masked`, `schema_version` | OD-03, NFR-S-07; a report must name its package |
| `Finding.statement` | Same | |
| `Finding.cited_event_ids` (min 1 always) | `cited_event_ids`, min 1 only for `evidence_supported` | FR-15 allows a hypothesis without a citation |
| (none) | `Finding.category` | FR-15 |
| `AnalysisReport.incident_id`, `findings`, `uncertainty`, `recommendations`, `generated_by` | Same names; recommendation strings must be non-empty | |
| `AnalysisReport.confidence` (0 to 1) | Same range, now defined as computed by the analysis component | OD-16 |
| (none) | `AnalysisReport.report_id`, `evidence_package_id`, `generated_at`, `model_id`, `prompt_version`, `summary`, `attack_type`, `sequence`, `weaknesses`, `impact`, `risk_justification`, `model_self_rating`, `schema_version` | FR-14, FR-19, OD-16 |
| `uncited_event_ids` checked findings only | Also checks `sequence[*].cited_event_ids` | Sequence steps cite events too |

## 7. Agreement checklist

| Contract | Agree with | Status |
|---|---|---|
| Event | C2 | pending |
| EvidencePackage | AI1 (T1-09), C2 | pending |
| AnalysisReport | AI1 (T1-09) | pending |
| ResponseAction | C5 | pending |
| AuditRecord | C5 | pending |
| Incident | C5, C1 | pending |

## 8. Review questions for AI1 (T1-09)

1. **Model input.** Which EvidencePackage fields should the model receive? The proposal is everything except `package_id` and `masked`, with the masked entity values.
2. **Model output.** The proposal is that the LLM returns `summary`, `attack_type`, `sequence`, `findings`, `weaknesses`, `impact`, `recommendations`, `risk_justification`, `uncertainty` and optionally `model_self_rating`. The backend fills `report_id`, `incident_id`, `evidence_package_id`, `generated_at`, `generated_by`, `model_id`, `prompt_version` and `confidence`. Is that split right for your LLM output schema?
3. **Citations.** Can every claim cite event IDs present in the package (`cited_event_ids` on findings and sequence steps)? Should `weaknesses`, `impact` and `risk_justification` carry citations too?
4. **Uncertainty and confidence.** Uncertainty is a required free-text section, plus the finding category on each finding. `confidence` is computed by the analysis component (OD-16), and `model_self_rating` is stored separately. Is that enough, or do you need a structured list of limitations?
5. **Grounding.** Does the contract support a later grounding validator? It provides entity values in the package (masked consistently), `citable_event_ids()` and `uncited_event_ids()`. What else would the validator need?

## 9. Open questions

| # | Question | Proposed default | Decided by |
|---|---|---|---|
| 1 | What is the `event_type` vocabulary? | C2 publishes the list; `unknown` when a type cannot be mapped | C2 |
| 2 | Is `host` one field, or separate source and destination hosts? | One field: the host the event was observed on or is about | C2, C3 |
| 3 | Can an incident be built from context events only? | No: at least one flagged event | C3, team |
| 4 | Do C3's `incident.created` and `incident.updated` audit types exist? | Yes, for FR-07 and FR-09 | C5, C3 |
| 5 | Do action states use snake_case (`simulated_succeeded`) rather than spec §12's hyphens? | snake_case, like every other enum | C5 |
| 6 | What format do masked tokens use? | `<kind>-<nn>` (`host-01`, `ip-01`, `user-01`), consistent within one package | C2, AI1 |
| 7 | Should a recommendation carry an optional catalogue scenario ID? | No: recommendations stay free text; C5 picks scenarios by lookup (C-10) | AI1, C5 |
| 8 | What are the incident types for C5's scenario lookup? | Come from T1-08; `incident_type` stays a free string until then | C3 (T1-08) |
| 9 | Is `notification.sent` incident-scoped? | No (`incident_id` optional) | C5 |
