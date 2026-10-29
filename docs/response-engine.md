# Response engine v0 (C5, Week 2)

| | |
|---|---|
| **Owner** | C5, Incident Response & Security Assurance |
| **Code** | `backend/app/response/`, migration `0003`, tests in `backend/tests/response/` |
| **Follows** | [response-workflow-spec.md](response-workflow-spec.md) (T1-13), [auth-and-threat-model.md](auth-and-threat-model.md) (T1-14) |
| **Week 2 gate (M2)** | Response-engine unit tests pass with a fake clock; every action is simulated and audited |

> **Every response action is a simulation.** The executor builds a record of what a scenario would do and changes nothing. No module of the engine core imports anything that can reach a network, a shell or another host, and a test checks that (AS-19).

## 1. What is in the package

| Module | What it does | Spec |
|---|---|---|
| `lifecycle.py` | The transition table T01 to T16 as data. `transition_for(state, trigger)` returns the transition or raises `TransitionRefused` (T15) | §3 |
| `freeze.py` | `check_freeze(incident, targets, window_open, config)`: every failing precondition, as reasons. `report_valid(incident)` | §5 |
| `targets.py` | `find_targets(incident, events, config)`: target host, external source IP, involved account | §6, §9 |
| `catalogue.py` | `lookup(targets, incident_type, confidence, config)`: the recommended or selected scenario, with its inputs | §9 |
| `executor.py` | `propose`, `decide`, `execute`: the simulated executor for S1 to S4, with an injectable failure rule for tests | §9, §10 |
| `response.toml` | 0.75 threshold, 60 s window, internal networks, catalogue v0 and the selection order | |
| `clock.py` | `DatabaseClock` (PostgreSQL `clock_timestamp()`) and `FakeClock` for tests | §7 |
| `models.py` | Tables of migration 0003 | §11, §12 |
| `engine.py` | `ResponseEngine`: register, analysis result, decisions, expiry, simulated execution, audit, reads | §3 to §11 |
| `expiry.py` | The expiry loop, started as a thread by the worker (`python -m app.worker`) | §7 |

## 2. Freeze rule

An incident freezes only when all of these hold. `check_freeze` returns every reason that fails, and the reasons go into the audit record of T04.

| # | Precondition | Code | Reason when it fails |
|---|---|---|---|
| 1 | Valid analysis: `analysis_status == succeeded` and a `latest_report_id` (decision D2) | `report_valid` | `analysis_not_valid` |
| 2 | Risk level High (score ≥ 70), from C3 | `is_high(incident.risk)` | `risk_not_high` (also when not scored) |
| 3 | Confidence ≥ 0.75 (OD-16; computed by AI1's analysis, never the model's self-rating) | `incident.confidence` | `confidence_below_threshold` |
| 4 | No open window for the incident (also a unique index in the database) | | `window_already_open` |
| 5 | A target host exists, because a freeze isolates a host (decision D3) | `find_targets` | `no_target_host` |

A failed analysis never freezes: it takes T05 and writes `analysis.failed`.

## 3. Targets (decision D3)

Only the incident's **flagged** events count; context events never become targets (OD-02).

| Target | Rule | Fixture incident A |
|---|---|---|
| Host | The `host` on the most flagged events; if no event has one, the internal `dst_ip` on the most | `web-01` (4 events; `db-01` has 3) |
| External source IP | The `src_ip` on the most flagged events that is **not** in `[network] internal` (RFC 1918 and loopback by default) | `203.0.113.10` |
| Account | The `user` on the most flagged events; a tie prefers a privileged account | `svc-db` (ties with `www-data`, but privileged) |

Remaining ties go to the alphabetically first value, so the same incident always gives the same targets. Python's `is_private` calls 203.0.113.0/24 private (it is a documentation range), which is why the engine uses the configured list instead.

## 4. Catalogue v0 and the lookup (decision D11)

| ID | Simulated behaviour | Needs | Selected automatically |
|---|---|---|---|
| S1 | Keep the host isolated (isolate it if not yet) and flag it for investigation | host | yes |
| S2 | Isolate the host and block the source IP | host, external source IP | yes |
| S3 | Isolate the host and disable the involved account | host, account | yes |
| S4 | Release isolation and raise monitoring | host | **no**, analyst only |

The lookup takes the first scenario of `[selection] order = ["S2", "S3", "S1"]` whose needs are met. It reads only stored values (targets, `incident_type`, confidence), so the recommendation made on entry to Awaiting Human Decision and the selection on expiry always agree. The inputs (incident type, confidence band, which targets exist) go into every `scenario.selected` and `scenario.no_match` record. At the W7 catalogue approval the order can become a table by incident type and confidence band without code changes.

## 5. How to call the engine (Week 3 wiring)

```python
from app.db import get_engine
from app.response.clock import DatabaseClock
from app.response.engine import DecisionType, ResponseEngine

response = ResponseEngine(get_engine(), DatabaseClock(get_engine()))
response.register(incident)  # T01, after C3 creates the incident
response.start_analysis(incident.incident_id)  # T02, when the analysis job starts
outcome = response.record_analysis(incident, events)  # T03 freeze, T04 no timer, or T05 failed
response.decide(incident_id, DecisionType.APPROVE, actor=user_id, role=user_role)
response.window_of(incident_id)  # what the countdown reads
response.audit_trail(incident_id)  # AuditRecord list, in order
```

- `record_analysis` takes the Incident as it is after the analysis (status, confidence, report ID set) and the incident's events.
- `decide` raises `DecisionRefused` with `reason` and `http_status` (403 not a SOC Analyst, 404 unknown incident, 409 window expired or wrong state, 422 missing scenario, data or comment). The refusal is already audited as `decision.refused`.
- Decisions are approve, reject, select (any of S1 to S4) and `no_action` (T16, comment required, only without an open window).
- Only the role `soc_analyst` may decide (D1.2, FR-39). The SOC Manager reviews only in the MVP (OD-24 proposal). Until login exists (Week 3), the caller passes the user ID and role.
- The expiry thread runs in the worker. `expire_due()` and `expire_window(window_id)` are safe to call twice or from two processes.

Rule TX: each step writes its transition, side effects and audit records in one transaction. A refused step changes nothing and is audited on its own.

## 6. Tables (migration 0003)

| Table | Holds | Notes |
|---|---|---|
| `incident_lifecycle` | Status, simulated isolation flag, targets, incident type, risk level, confidence, recommended scenario | Until incidents are stored (Week 3, decision D1); then the status moves onto the incidents table |
| `incident_status_history` | Every status change: transition ID, previous and new status, actor, cause, time | FR-31 |
| `response_windows` | `window_id`, `incident_id`, `status` (`open`, `decided`, `expired`), `started_at`, `deadline_at`, `recommended_scenario_id`, `closed_at` | One open window per incident (partial unique index) |
| `response_actions` | Each simulated action as the ResponseAction contract JSON | A check constraint forces `simulated = true` |
| `audit_records` | Each AuditRecord | A trigger refuses UPDATE and DELETE (C-14, decision D7) |

## 7. Clock and expiry (decisions D4 and D5)

- The running system takes every time from PostgreSQL (`SELECT clock_timestamp()`), so the API and the worker share one clock. `deadline_at = started_at + 60 s`.
- The conditional updates compare against that time: a decision only closes a window whose `deadline_at` is still in the future; the expiry only closes one whose `deadline_at` has passed. Whichever commits first wins. No grace period.
- Tests use `FakeClock` and move it by hand (`clock.advance(59.999)`), so no test waits.
- The expiry loop polls every 0.5 s on its own thread in the `worker` container, so a long ingest job never delays an expiry. After a restart it processes every overdue window once; the audit record keeps the real `deadline_at` and the delay (`late_ms`).

## 8. Handoff to C4 (state names and deadline field)

**Incident states** (`IncidentStatus`, values as sent): `new`, `under_analysis`, `awaiting_human_decision`, `response_in_progress`, `escalated`, `resolved`, `closed`. Display labels are in `IncidentStatus.label`.

**Response window** (`ResponseEngine.window_of(...).as_json()`), the same fields as your `ResponseWindow` type in `frontend/src/api/responseWindows.ts`:

```json
{
  "incident_id": "inc-…",
  "window_id": "win-…",
  "status": "open",
  "started_at": "2026-11-02T09:15:30.250Z",
  "deadline_at": "2026-11-02T09:16:30.250Z",
  "server_time": "2026-11-02T09:15:42.750Z",
  "recommended_scenario_id": "S2"
}
```

**Decisions**: your `DecisionType` (`approve`, `reject`, `select`) matches; the engine adds `no_action` (T16, comment required). Refusal reasons map to the HTTP codes your stub already uses (403, 409, 422). The HTTP endpoints and the WebSocket come in Week 3 with login; until then keep the stub.

## 9. Handoff to AI1 (report valid)

The freeze rule reads the Incident contract, not a new field: **report valid** = `analysis_status == "succeeded"` and `latest_report_id` set; **confidence** = `Incident.confidence` (0 to 1, set exactly when the analysis succeeded). If your pipeline marks an analysis as failed, set `analysis_status = "failed"`; it never freezes.

## 10. Decisions applied (C5 Week 2)

| # | Decision |
|---|---|
| D1 | C5 keeps the lifecycle state in `incident_lifecycle` until incidents are stored (Week 3) |
| D2 | Report valid = succeeded analysis with a report ID |
| D3 | Target rules of section 3; no target host means no freeze |
| D4 | One clock: database time in the app, fake clock in tests |
| D5 | Expiry loop on a thread in the worker process |
| D6 | Simulated failures only through an injected failure rule; no environment switch |
| D7 | `audit_records` is append-only through a database trigger |
| D8 | Engine and tests in Week 2; HTTP endpoints and WebSocket in Week 3 |
| D9 | No login in Week 2; the caller passes user ID and role; only `soc_analyst` decides |
| D10 | No 30-second reminder until OD-19 is decided (W5) |
| D11 | Catalogue lookup keeps the v0 entity rule, in `response.toml` |
| D12 | T16 is built as decision `no_action` |

## 11. Acceptance-test ideas found this week (for the Week 8 suite)

- AS-09: freeze exactly at confidence 0.75 and not at 0.7499; an unscored incident never freezes.
- AS-10: two workers expire the same window at once and only one scenario runs; a decision 1 ms before the deadline wins, one at the deadline is refused with 409.
- AS-10: worker down for 5 minutes, then one expiry with the real deadline in the audit record.
- AS-14: every audit record of a full path validates against the AuditRecord contract, and UPDATE or DELETE on `audit_records` fails.
- AS-19: the engine core imports no network or shell module; every stored action has `simulated = true`.
- New: an incident with no host (fixture F) can neither freeze nor run a scenario.
