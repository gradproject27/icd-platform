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
| `GET /incidents/{id}/report` | **always 404 `report_not_available` for now**: no AI report is stored anywhere yet (gap G3, C1/AI1) | none |
| `GET /incidents/{id}/audit` | `AuditTrail`: `{items: AuditRecord[]}` in written order | C5 `audit_records` |
| `GET /response-windows/{id}` | `ResponseWindow`, times with milliseconds (spec section 7); 404 `not_found` when the incident never had a window | C5 `window_of` |
| `GET /incidents/{id}/decision` | `DecisionRecord` of the latest recorded decision; 404 `not_found` when none | C5 audit trail and actions |
| `POST /incidents/{id}/decisions` | body `DecisionRequest` `{decision, scenario_id, window_id, comment}` → **201** `DecisionRecord` | C5 `decide` |
| `WS /ws/response-windows?incident_id=` | `response_window.opened`, `.decided`, `.expired` (fields of spec section 7) | C5 `window_of`, read every 0.5 s |

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
- **AI reports are not stored** (no table, no endpoint): C1/AI1.
- **UNSW-NB15 flows have no host** (C2-D8) and documentation-range IPs, so C5's target rule finds no target and they never freeze.
- **Login** (C5, T2-15) replaces the development identity.
