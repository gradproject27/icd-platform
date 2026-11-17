# C4 Step 8 views: gaps and proposed decisions

| | |
|---|---|
| **Owner** | C4, Dashboard |
| **Branch** | `feature/c4-step8-views`, from `feature/c4-step8-frontend` (`7394882`) |
| **Status** | **Approved by the team lead on 17 Nov 2026, with the changes in section 0.** |
| **Sources** | [response-workflow-spec.md](response-workflow-spec.md) sections 3, 5, 8, 11; [auth-and-threat-model.md](auth-and-threat-model.md) A3 and its note 3; [wireframes.md](wireframes.md) sections 3, 4.4, 4.6, 6; [correlation-and-risk-design.md](correlation-and-risk-design.md) sections 9.3, 11, 13, 15; [contracts-v1.md](contracts-v1.md) (`AuditRecord`, `AuditEventType`); [api-incidents.md](api-incidents.md); `backend/app/api/incidents.py`; `backend/app/response/engine.py`; `frontend/src/` |

The Step 8 gaps document (`00-step8-gaps-and-decisions.md`) was not reachable from this machine. This document starts at S8-D8, as asked, and uses [api-incidents.md](api-incidents.md) section 3 as the list of known gaps.

## 0. What the team lead approved (17 Nov 2026)

| Decision | Outcome |
|---|---|
| S8-D8 Notifications | Approved as recommended, except the poll interval: **every 3 s**, not 10 s |
| S8-D9 `GET /me` | Approved |
| S8-D10 Review queue | Approved with one change: the **Escalated group is shown to the SOC Analyst and the SOC Manager**. The analyst acts on it through T12 (select or approve) and T16 (`no_action`). Reject is dropped on Escalated, as proposed |
| S8-D11 Audit view | Approved |
| S8-D12 Explanation view | Approved |
| S8-D13 Configuration view | Approved; visible to **Security Engineer and System Administrator only** |
| S8-D14 Graph view | Approved |
| S8-D15 Backend changes | Approved |
| S8-D16 PR split | Approved |
| Screenshots | Kept local, not committed |
| Order of work | As proposed: D9, D10, D8, D11, D12, D13, D14 |

Gaps to record besides those in section 2:

- **SOC Analyst audit review of "own incidents only"** (A3, OD-24 proposal) needs login (C5, T2-15). Until then the analyst sees every incident's trail.
- **The System Administrator cannot view incidents until OD-24** (A3). Neither the server nor the existing incident pages enforce this yet. It is recorded as a gap only; no page is changed for it in this work. The new views follow the rules approved above.

## 1. Facts found while reading, which change the options

| # | Fact | Where | Why it matters |
|---|---|---|---|
| F1 | The WebSocket is **per incident**: `WS /ws/response-windows?incident_id=` requires `incident_id`. It only sends `response_window.opened`, `.decided` and `.expired`. | `incidents.py` `window_socket` | It cannot tell the dashboard about an incident the user is not looking at, so it cannot drive notifications on its own (option (a) of the prompt). |
| F2 | C5's engine already writes `notification.sent` audit records at T03 (`freeze_started`, recipients `soc_analyst,soc_manager`), T09 (`no_match`, `soc_manager`) and T11 (`simulated_action_failed`, `soc_analyst,soc_manager`). | `engine.py` lines 480, 764, 860 | The notification data exists. Only a way to read it across incidents is missing. |
| F3 | The engine writes **no** `response_window.reminder` (OD-19, still proposed). | `engine.py` | The 30-second reminder is not a backend notification today. |
| F4 | The dashboard **does not know who the user is**. The role (`ICD_DEV_ROLE`) is read only on the server, in `POST /decisions`. No endpoint returns it. | `incidents.py` `dev_identity`; `frontend/src` | No role rule (escalation view for the SOC Manager only, audit review, configuration) can be applied in the dashboard without a new read. |
| F5 | The **risk-explanation content is already on the detail page**: the RiskBox shows the factor table, top contributors, flags, `config_version`, `computed_at` and `risk_justification`. | `IncidentDetailPage.tsx` lines 85 to 140 | The explanation view is mainly about presentation, labels and the freeze-gate reasons, not new data. |
| F6 | **"Not in data" factors no longer exist.** Since the 29 Oct method the score always has exactly two factors, `likelihood` and `impact`. Assumptions are `flags` (`asset_unknown`, `outcome_unknown`, `severity_default`). | correlation-and-risk-design.md 9.3 and Q13 | Wireframes question 9 is closed by C3's design. The view shows the flags instead. |
| F7 | `risk.toml` has **no factor labels**. The design asks that the impact row read as "points removed by the asset's impact", not as a weighted share. | `risk.toml`; design 9.3 | Wireframes question 6 has no C3 label source. Labels would be C4 text. |
| F8 | The **freeze-gate reasons are in the audit trail**. The `status_changed` record of T03 and T04 carries `freeze`, `reasons`, `risk_level`, `confidence` and `recommended_scenario_id` in `details`. | `engine.py` `_record_analysis` | The explanation view can say, from real data, why an incident did or did not get a response window. |
| F9 | Medium risk goes to `Awaiting Human Decision` with **no window, no notification and no timeout** (T04, FR-25 review). In that state C5 allows `approve`, `reject`, `select` and `no_action`. In `Escalated` it allows `approve`, `select` and `no_action`, but not `reject`. `no_action` needs a comment and no open window. | spec 5 and T04, T16; `engine.py` `_decide` | Medium never has a window, so a review list needs no per-incident window calls. The panel today offers only approve, reject and select (`proposed.ts` `DecisionType`). |
| F10 | **No configuration endpoint exists.** Incidents carry `risk.config_version` and `correlation_config_version`. Thresholds (40 and 70) and other values are only in `risk.toml` and `correlation.toml`. | design 11 and 13 | A configuration view can show versions from real data, but not the thresholds, unless an endpoint serves them. |
| F11 | **On the real stack every new view is mostly empty this week.** Nothing registers stored incidents with C5's engine yet, so real incidents stay `new`, with no window, notification, decision or audit record (api-incidents.md section 3). | api-incidents.md 3 | The views can be fully tested only with tests that drive the engine, as Step 8 did. In a browser on uploaded UNSW-NB15 data they show their empty states. |

## 2. One row per item

| # | Item | What the spec or wireframe asks for | Backend data that already exists | What is missing | Owner of the missing part |
|---|---|---|---|---|---|
| 1 | Notifications | A dashboard notification to the SOC Analyst and the SOC Manager at T03 (freeze), to the SOC Manager at T09 (no match) and to both at T11 (simulated failure), audited as `notification.sent` (spec T03, T09, T11, section 11; FR-26, FR-46). A notification is not the "receive escalations" permission (auth A3 note 3). No wireframe exists. | `notification.sent` records in `GET /incidents/{id}/audit` (F2), with `details.recipients` and `details.reason` | A cross-incident read (F1); the user's role, to show only notifications meant for that role (F4); the 30-second reminder (F3) | Read endpoint: C4 wiring on C5's table (S8-D8, S8-D15). Reminder: C5 (OD-19). Real records: C1/C5 `register` wiring (F11) |
| 2 | Medium-risk review | Medium: `Awaiting Human Decision`, FR-25 review, no timeout. High below 0.75: no timer. Low: listed, no notification (spec section 5). An analyst can end an incident that needs no response with `no_action` and a comment (T16). No wireframe exists; 4.6 covers the "No window" state. | `GET /incidents` (status, `risk.level`, `confidence`); `GET /response-windows/{id}`; `POST /incidents/{id}/decisions` with `no_action` (api-incidents.md 2) | A list of incidents waiting for review; `no_action` on the panel (F9); the role, to hide decision controls for non-analysts (F4) | C4 only, apart from the role read (S8-D9) |
| 3 | Configuration view | Wireframes have no screen. A3: Security Engineer configures system settings and scenarios (D7.5); System Administrator configures thresholds, timing and policies (OD-24 proposal). The 60-second window is fixed (A3 note 1). | `risk.config_version`, `correlation_config_version` on every incident | Thresholds and other configured values: no endpoint (F10); the role (F4) | `GET /config/risk`: C3 (S8-D13) |
| 4 | Audit view | Wireframes have no screen. A3: "Review audit records": SOC Analyst, own incidents only (OD-24 proposal); System Administrator (OD-24 proposal); SOC Manager and Security Engineer denied. Records are append-only (C-14). Action records carry `simulated: true` and `SIMULATED` (NFR-SF-07). | `GET /incidents/{id}/audit` (`AuditTrail`: `event_type`, `actor`, `actor_role`, `occurred_at`, `result`, `simulated`, `details`) | A global audit list needs `GET /audit`; "own incidents" needs login (T2-15); the role (F4) | `GET /audit`: C5 (audit store) or C1 (S8-D11). Login: C5 (T2-15) |
| 5 | Explanation view | Wireframes 4.4: factor table, `config_version`, `computed_at`, `risk_justification`; question 6 (labels); question 9 ("not in data"). NFR-SF-05, C-17: say why events were grouped and what sets the risk. | `risk.factors` (with `reason`), `likelihood`, `impact`, `flags`, `top_contributors`, `config_version`, `computed_at`; `link_keys` per event; `correlation_config_version`; `split`; freeze-gate reasons in `status_changed` details (F8) | `risk_justification`: no report is stored (gap G3). Labels from C3's configuration (F7). "Not in data" is closed (F6). | Report storage: C1/AI1. Labels: C3, or C4 text (S8-D12) |
| 6 | Graph view (optional) | No wireframe exists. | `entities` (`GET /incidents/{id}`); `event`, `role`, `link_keys` (`GET /incidents/{id}/events`) | Nothing on the backend | C4 only |

## 3. Proposed decisions

Each decision is **proposed** until the team lead approves it.

### S8-D8. Notifications: source, place and persistence

**Source.**

| Option | What it means | For | Against |
|---|---|---|---|
| (a) Frontend only | Every 10 s, read `GET /incidents`, then `GET /incidents/{id}/audit` for each incident in `awaiting_human_decision` or `escalated`, and keep the `notification.sent` records | No backend change | One call per waiting incident every 10 s (up to 1000). The per-incident WebSocket (F1) does not help. |
| (b) New `GET /notifications?after=` | A read-only endpoint that returns `notification.sent` audit records across incidents, newest first, at most 100, optionally after a `record_id`. The dashboard polls it every 10 s. | One cheap call. It reads C5's table only, with no new rule, in the same way as `GET /incidents/{id}/audit`. | A backend change (S8-D15) |
| (c) New `WS /ws/notifications` | A push channel | Instant | Larger backend work in C5's area, and it still needs (b) to read what came before a reload. |

**Recommendation: (b).** It is the smallest change that scales. It also stays "C5's data, C4's read", like the other Step 8 routes. A 10-second poll is enough, because the countdown page already has its own live WebSocket.

**Place.** A **"Notifications (n)" button in the header**, next to the navigation, with the unread count as text (not colour alone). It opens a panel that lists, for each notification:

- the time;
- the incident (as a link);
- the reason, in plain words: "Response window opened (SIMULATED isolation)", "Window expired, no scenario matched: escalated", "Simulated action failed: escalated";
- the recipient roles.

A new notification also shows a short toast with `role="status"`, which is not focusable and closes after 8 s.

**Who sees what.** The user sees only notifications whose `recipients` include their role, read from `GET /me` (S8-D9). Without a role, the panel lists all notifications and says "Signed-in role unknown: showing all".

**Persistence.** The notifications themselves persist, because they are audit records. The "read up to" marker is kept in the browser's `localStorage` under the last seen `record_id`, so the unread count survives a reload in the same browser. It is per browser, not per user, until login (T2-15) can store it on the server.

**Out of scope.** The 30-second reminder (OD-19) is not built. C5 writes no reminder record (F3). It stays a C5 gap.

### S8-D9. The dashboard needs to know the role: `GET /me`

Every role rule in items 1 to 5 needs the role, and the dashboard cannot read it today (F4).

| Option | What it means |
|---|---|
| (a) New `GET /me` | Returns `{user, role}` from `ICD_DEV_USER` and `ICD_DEV_ROLE` (the same `dev_identity()` the decision route uses), or 401 `not_authenticated` without them. Login (T2-15) later replaces how it is filled, not its shape. |
| (b) A Vite build variable | A `VITE_ICD_ROLE` setting in the frontend. It can disagree with the server. |
| (c) No role rules this week | Show every view to everybody, and record the role rules as a gap. |

**Recommendation: (a).** The role then has a single source, the server, as FR-39 asks. The dashboard uses the role **only to hide or explain**. Every permission stays checked on the server where one exists, and where none exists that is recorded as a gap (C-04: hiding is never the only protection).

### S8-D10. Medium-risk review: a Review queue page, and `no_action` on the panel

**Page.** A new **"Review"** entry in the navigation, at `/review`. It lists incidents in `awaiting_human_decision` from `GET /incidents`, in three labelled groups:

1. Medium, FR-25 review;
2. High without confidence ≥ 0.75, which has no timer;
3. Low, listed only.

Each group is sorted oldest first, so nothing waits for ever. None of the three groups ever has a window (T04). High incidents with a window are not on this page; they are reached from the countdown and the notifications.

| Option | For | Against |
|---|---|---|
| (a) Its own page `/review` | One place that says "these wait for you and no timer will act". It matches the role card item. | One more page |
| (b) A preset filter on the incident list, such as `?status=awaiting_human_decision&level=medium` | No new page | It hides FR-25 review inside a generic list and cannot show the three groups with their meaning |

**Recommendation: (a).** It reuses the list's row component and the same `GET /incidents` read. Filters stay in the browser (D8).

**Which decisions.** The review row links to the existing Pending decision panel. The panel gains the fourth option that C5 already supports: **"No response needed"** (`no_action`). It:

- needs a comment, enforced in the form and by the server (422 `validation_error`);
- is offered only when there is no open window (otherwise the server refuses it with 409 `window_open`);
- is offered in `awaiting_human_decision` and `escalated`.

The panel also stops offering **reject** in `escalated`, because C5 refuses it there (F9).

None of the options are offered to roles other than `soc_analyst`. Those roles see the line "Only a SOC Analyst can decide" (wireframes 4.6, read-only state).

**Escalation view (auth A3 note 3).** The Review page gets a fourth group, **"Escalated"**, shown only when the role is `soc_manager` (D7.2). **The server does not restrict `GET /incidents` by role.** That is a gap for C5 and login (T2-15), and the page says so in the code comment and in api-incidents.md section 3.

### S8-D11. Audit view: per incident now; global list as a gap

| Option | What it needs |
|---|---|
| (a) Per-incident page `/incidents/:id/audit` | The existing `GET /incidents/{id}/audit`. No backend change. |
| (b) Global list `/audit` | A new `GET /audit` with paging and filters. Rule A3 "own incidents only" for the SOC Analyst needs a real user (login). |

**Recommendation: (a) this week; (b) recorded as a gap** for C5, who owns the audit store, and for login (T2-15).

**Content.** A table in written order. Each row shows:

- the time (`occurred_at`, with UTC on hover);
- the event type, as a label;
- the actor and the actor's role;
- the result;
- the details, as `key: value` text, never raw JSON.

**SIMULATED.** Every row with `simulated: true` shows the text badge `[SIMULATED]` in the event column (NFR-SF-07, wireframes 2.4).

**Filters**, held in the URL query like the incident list:

- event group: Lifecycle, Decisions, Response window, Simulated actions, Notifications;
- actor: system or user;
- result.

**Where it is linked from.** An "Audit trail" link on the incident detail page.

**Who sees it.** `soc_analyst` and `system_administrator` (A3, OD-24 proposal). The other roles see "Your role cannot review audit records". The endpoint itself does not check the role, so this is the same gap as in S8-D10.

### S8-D12. Explanation view: its own page, built from real fields only

| Option | For | Against |
|---|---|---|
| (a) Extend the RiskBox on the detail page | No new route | The detail page is already long. The freeze-gate reasons and the grouping need an audit read and an events read, which the detail page does not do for the box. |
| (b) Its own page `/incidents/:id/explanation`, linked from the RiskBox | Room for the three "why" questions; the RiskBox stays a summary | One more page |

**Recommendation: (b).** The page answers three questions, each from real fields only.

1. **Why this risk score.** The two factors, with C4 labels and the raw name on hover (wireframes question 6; F7):
   - `likelihood` reads "Evidence strength (L)";
   - `impact` reads "Points removed by the asset's impact (I)", as design 9.3 asks.

   Each factor's own `reason` is shown below it. Then come:
   - the flags, in plain words, for example `asset_unknown` reads "Asset not in the inventory: worst-case impact assumed";
   - the top contributors, each linked to its event on the timeline;
   - `config_version` and `computed_at`;
   - `risk_justification` from the report, which reads "Not determined: no AI report is stored yet" while gap G3 is open.

   "Not in data" is not shown, because the method has no excluded factors (F6).
2. **Why these events were grouped.**
   - The count of events per link key (host, user, source IP, destination IP), from `link_keys`;
   - the first event;
   - `correlation_config_version`;
   - the size-cap split, when `split` is set.
3. **Why there is, or is not, a response window.** The latest `status_changed` record with gate details (F8): risk level, confidence, the freeze reasons in plain words, and the recommended scenario (catalogue lookup, with the label "advice, not an action", C-10). Before the engine tracks the incident, this reads "Not analysed yet".

The labels are C4 text in `labels.ts`. **If C3 prefers to own the factor labels**, they move to `risk.toml` and a configuration read later (S8-D13 (b)). I record that as an open question for C3, not as a change to C3's files.

### S8-D13. Configuration view

| Option | What it shows | Backend |
|---|---|---|
| (a) Read-only page `/configuration` from what incidents carry | The `risk.config_version` and `correlation_config_version` values seen across `GET /incidents`, with the count of incidents per version (AS-04 traceability: "was everything scored with the same configuration?"); the response window as "60 seconds, fixed, not configurable (OD-17)"; the catalogue S1 to S4 with its spec text, as the panel already shows it | None |
| (b) New read-only `GET /config/risk` | Thresholds, severity, confidence and decay values from `risk.toml` and `correlation.toml` | C3 owns the data and the shape |
| (c) Gap only | Nothing | None |

**Recommendation: (a) now, and (b) recorded as a gap for C3.** Showing the thresholds (40 and 70) as literals in the dashboard would be data the API does not send, so the page says "Thresholds and weights are not served by the API yet (C3)" instead.

**Who sees it.** `security_engineer` and `system_administrator`, the two configuring roles in A3. The other roles see "Your role cannot view the configuration". A3 has no "view configuration" row, so deny by default applies; **this needs your confirmation.**

### S8-D14. Graph view (optional)

| Option | For | Against |
|---|---|---|
| (a) Entity graph in plain SVG, at `/incidents/:id/graph` | No new dependency. The layout is deterministic and simple: events in time order in one column, entities (host, user, IP) in a second column, with a line for each event-to-entity link. Flagged and context events differ in text (`FLAGGED` or `context`), not colour alone. The edges that are `link_keys` (the reason for grouping) are solid; other fields are dashed. A table of the same edges sits under it for screen readers. | Readable only up to about 50 events. Above that it shows the first 50 and says so. |
| (b) A graph library, for example `cytoscape` | Real force layouts | **A new npm dependency, which is your decision.** It is heavy for one optional view. |
| (c) Skip it this week | Time goes to items 1 to 5 | The role card item stays open |

**Recommendation: (a), built last, only after items 1 to 5 pass every check.** If time runs out, (c), and the item is recorded as not done.

### S8-D15. Backend changes

If S8-D8 (b) and S8-D9 (a) are approved, these are the only backend changes. Both are read-only. Neither changes C3's risk calculation, C5's engine rules or AI1's code.

| Change | Files |
|---|---|
| `GET /me` → `CurrentUser {user, role}`; 401 `not_authenticated` without the dev identity | `backend/app/api/incidents.py` (next to `dev_identity`); `schemas.py` (`CurrentUser`, a new `ErrorCode`); `export.py` SHAPES; `docs/api/examples/current-user.json`; regenerated `docs/api/schemas/`; `frontend` `npm run contracts:gen`; `backend/tests/api/test_me.py`; `docs/api-incidents.md` |
| `GET /notifications?after=&limit=` → `NotificationList {items: AuditRecord[]}`: `notification.sent` records, newest first, at most 100 | A new read-only query on C5's audit table (`app/response/models.py`) in `backend/app/api/incidents.py`, with no change to `engine.py`; `schemas.py`; `export.py`; `docs/api/examples/notification-list.json`; regenerated schemas and types; `backend/tests/api/test_notifications.py`; `docs/api-incidents.md` |

**Recommendation:** put them in this work (see S8-D16) and ask C5 to review, because `GET /notifications` reads C5's table. **Not in this work**, recorded as gaps with their owners:

- `GET /audit` (C5);
- `GET /config/risk` (C3);
- the reminder event (C5, OD-19);
- role checks on GET routes (C5, T2-15);
- AI report storage (C1/AI1);
- `register` after correlation (C1/C5).

### S8-D16. PR split

| Option | What it means |
|---|---|
| (a) Backend commits on `feature/c4-step8-views`, then frontend commits | The three-PR stack of the prompt stays as it is (A, B, C). PR C has one backend commit and the frontend commits, kept as separate commits, and C5 is asked to review the backend commit. |
| (b) Backend commits added to `feature/c4-step8-api-wiring` | All backend work sits in PR A, but `feature/c4-step8-frontend` must then be rebased onto it (history rewrite of a pushed branch). |
| (c) A fourth branch for the backend | Four stacked PRs |

**Recommendation: (a).** There is no rebase of pushed branches, the stack stays three PRs, and the backend part is one small commit that is easy to review alone.

## 4. Questions for you besides the decisions

1. **Configuration role** (S8-D13): only `security_engineer` and `system_administrator`?
2. **Screenshots** (Phase 3): may they be committed to `docs/c4-step8-screens/`? The default is to keep them local.
3. **Order of work if time runs short:**
   1. S8-D9 (`/me`);
   2. S8-D10 (review and `no_action`);
   3. S8-D8 (notifications);
   4. S8-D11 (audit);
   5. S8-D12 (explanation);
   6. S8-D13 (configuration);
   7. S8-D14 (graph).

   Agree?
