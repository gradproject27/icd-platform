# Incident, response-window and decision API (Step 8)

Owner of the wiring: C4 (Step 8, decision S8-D1), on code owned by C1 (incident storage), C3 (correlation, risk) and C5 (response engine). Reviewers: C1/C5 owner and C3. Shapes: the ones C4 proposed in #22 and #23, adopted under W3-D9; JSON Schemas in [`docs/api/schemas/`](api/schemas/), examples in [`docs/api/examples/`](api/examples/), both generated or checked by `backend/tests/api/test_api_shapes.py`.

The routes in `backend/app/api/incidents.py` only **read and pass on** what is stored. They compute no risk score, pick no scenario and change no rule of the response engine.

## 1. Endpoints

Paths as the API sees them; the dashboard calls them under `/api` (same origin, A2.14). Every error uses C1's shape `{"error": {"code", "message"}}`.

| Method and path | Answer | Source |
|---|---|---|
| `GET /incidents?upload_id=` | `IncidentList`: `{items: IncidentSummary[]}`, newest first event first, at most 1000. `upload_id` is optional | `incidents` table (C1, migration 0005) |
| `GET /incidents/{id}` | `IncidentSummary`: `{incident, entities, recommended_scenario_id}`; 404 `not_found` | as above |
| `GET /incidents/{id}/events` | `IncidentEventList`: `{items: [{event, role, link_keys}]}`, oldest first | `incident_events` + `events` |
| `GET /incidents/{id}/events/{event_id}/original` | `OriginalRecord`: `{event_id, record_ref, source_file, line}`; 404 `original_not_available` when the uploaded file is gone or the event's `record_ref` is not a line (the `fixture` dataset) | the uploaded file, `read_original` (C2) |
| `GET /incidents/{id}/report` | `AnalysisReport` (contracts) that the incident's `latest_report_id` names, **un-masked for display**: host, user and IP tokens in the text fields are replaced with the real values from the package's masking map (C2-D7). The stored copy stays masked; the un-masked copy is never stored. Header `X-ICD-Report-Masked: 1` when a token is still in the text (map missing, or a token the model invented) (C4-D1). 404 `report_not_available` until the analysis job has stored a valid report | `analysis_reports` (AI1, migration 0006) via `latest_report`; `masking_maps` via `load_masking_map` + `unmask_report` (C2) |
| `GET /incidents/{id}/audit` | `AuditTrail`: `{items: AuditRecord[]}` in written order | C5 `audit_records` |
| `GET /incidents/{id}/containments` | `ContainmentList`: `{items: SimulatedContainment[]}`, the simulated IP blocks the incident started or last extended, oldest first, each with `ends_at`, `status` (`active`, `reverted`), `offence` and `simulated: true` (P2, [response-engine.md](response-engine.md) section 7a). Empty for an incident without a succeeded S2; 404 `not_found` for an unknown incident | C5 `simulated_containments` (migration 0007) via `containments_of` |
| `GET /response-windows/{id}` | `ResponseWindow`, times with milliseconds (spec section 7); 404 `not_found` when the incident never had a window | C5 `window_of` |
| `GET /incidents/{id}/decision` | `DecisionRecord` of the latest recorded decision; 404 `not_found` when none | C5 audit trail and actions |
| `POST /incidents/{id}/decisions` | body `DecisionRequest` `{decision, scenario_id, window_id, comment}` → **201** `DecisionRecord` | C5 `decide` |
| `WS /ws/response-windows?incident_id=` | `response_window.opened`, `.decided`, `.expired` (fields of spec section 7) | C5 `window_of`, read every 0.5 s |
| `GET /me` | `CurrentUser`: `{user, role}` the API acts as; 401 `not_authenticated` without the development identity (S8-D9) | `ICD_DEV_USER`, `ICD_DEV_ROLE` |
| `GET /notifications?after=&limit=` | `NotificationList`: `{items: AuditRecord[]}`, C5's `notification.sent` records of every incident, newest first, `limit` 1 to 100 (default 50); with `after` (a `record_id`), only records written after it; an unknown `after` is ignored (S8-D8) | C5 `audit_records`, read only |
| `POST /incidents/{id}/analysis` | body `{force}` (optional; `force: true` skips the report cache) → **202** `JobAccepted`, header `Location`; an analysis already queued or running for the incident is returned instead of a second one; 404 `not_found`. The ingest job already queues one analysis per incident, so this is for a re-run (C1 decision F8) | `jobs` (kind `analysis`), [prototype-architecture.md](prototype-architecture.md) |

**Entities** are the distinct `host`, `user`, `src_ip` and `dst_ip` values of all the incident's events, flagged and context (as C4's stub did; C3 may restrict them to flagged events).

**Status.** Once C5's engine tracks an incident (`incident_lifecycle`), its status replaces the one stored with the incident, and `recommended_scenario_id` is the engine's catalogue recommendation. Until then the status is the stored one (`new`) and the recommendation is `null`.

## 2. Decisions

- `decision`: `approve` (takes the recommended scenario; a different `scenario_id` is refused), `reject` (no `scenario_id`), `select` (`scenario_id` S1 to S4), or `no_action` (T16, comment required, only without an open window).
- `window_id`: the open window the analyst answers, or null.
- **Who decides.** There is no login yet (C5, T2-15). The API decides as the development identity in `ICD_DEV_USER` and `ICD_DEV_ROLE` (decision S8-D4; `.env.example` sets `analyst-dev` / `soc_analyst`). Without them every decision is 403 `not_authorized`. Only `soc_analyst` may decide (D1.2, FR-39).
- An approve or select runs the simulated action at once, so the 201 answer already carries the `ResponseAction` in its final state and the incident `resolved` (or `simulated_failed`).

| Refusal (C5's reason) | HTTP | `error.code` |
|---|---|---|
| no identity, or not a SOC Analyst | 403 | `not_authorized` |
| incident unknown to C5's engine | 404 | `not_found` |
| decision already recorded | 409 | `already_decided` |
| other wrong state (`wrong_state`) | 409 | `not_awaiting_decision` |
| window expired, at or after `deadline_at` | 409 | `window_expired` |
| `window_id` is not the open window | 409 | `window_mismatch` |
| `no_action` while a window is open | 409 | `window_open` |
| bad body, no recommendation, wrong or missing scenario, missing data or comment | 422 | `validation_error` |

Every refusal is also in the audit trail as `decision.refused`.

## 3. Gaps this does not close

- **Nothing registers stored incidents with C5's engine yet**, and no analysis job runs (no HPC; only the mock LLM). So real incidents stay `new`, have no window and cannot be decided until C1/C5 wire `register` after correlation and the analysis job calls `record_analysis` (Week 3 T3 wiring). Tests and the browser check drive the engine directly.
- **Reports are served, but only once something stores them.** The report endpoint reads `analysis_reports`; the analysis job that calls `analyze_incident` after correlation is C1's.
- **UNSW-NB15 flows have no host** (C2-D8) and documentation-range IPs, so C5's target rule finds no target and they never freeze.
- **Login** (C5, T2-15) replaces the development identity.
- **No read checks a role.** The dashboard hides the views a role may not see (A3), but `GET /incidents`, `/audit`, `/notifications` and the others answer everybody. Server-side role checks on reads come with login: C5 (T2-15).
- **SOC Analyst audit review of "own incidents only"** (A3, OD-24 proposal) needs a real user to compare with: login, C5 (T2-15). Until then the analyst sees every incident's trail.
- **The System Administrator cannot view incidents until OD-24** (A3). Neither the server nor the incident pages enforce this yet: C5 with OD-24.
- **No global audit list** (`GET /audit` with paging and filters): C5. The dashboard shows one incident's trail.
- **No configuration read** (`GET /config/risk`: thresholds, weights and other values of `risk.toml` and `correlation.toml`): C3. The configuration view shows only the versions the incidents carry.
- **No 30-second reminder** (`response_window.reminder`, OD-19, proposed): C5's engine writes none, so neither the countdown nor the notifications show one.
- **The notification "read" marker is per browser** (`localStorage`), not per user, until login can store it on the server: C5 (T2-15).
- **Factor labels are C4 text** (`frontend/src/labels.ts`): C3's configuration has none (wireframes question 6). If C3 adds labels, the dashboard reads them instead.
