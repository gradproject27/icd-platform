# Dashboard wireframes (low fidelity)

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **Owner** | C4, Frontend & Security Dashboard |
| **Task** | T1-12 (Week 1). Built from Week 2 on top of the T1-10 skeleton |
| **Status** | Draft. Items marked **(proposed, needs C1/C2/C5 agreement)** have no contract yet |
| **Sources** | [contracts-v1.md](contracts-v1.md) and `contracts/schemas/`; [correlation-and-risk-design.md](correlation-and-risk-design.md); [response-workflow-spec.md](response-workflow-spec.md) sections 2 and 5 to 10; [auth-and-threat-model.md](auth-and-threat-model.md) A2 and A3 |

## 1. Purpose and scope

This document gives low-fidelity wireframes for the ICD dashboard. It covers the five requested areas (Upload, Incident list, Incident detail, AI report panel, Pending decision) and the Login shell.

The wireframes fix **what each screen shows and what the user can do there**. They are also the information architecture for Week 2: every piece of information names the contract field it comes from.

It is not:

- final styling: there are no colours, fonts or sizes;
- an API design: endpoints are not defined here;
- a contract change: every field comes from `contracts/schemas/` or a merged document. Anything else is marked as proposed and listed in section 6.

**Who owns what.** C4 owns the presentation only. Every value comes from the backend:

- risk scores, levels and factors come from C3's code (OD-04, OD-05). The LLM writes only the justification;
- the response deadline comes from the server's `deadline_at`. The browser never starts its own 60-second timer (NFR-P-09);
- the recommended scenario comes from C5's deterministic catalogue lookup, never from LLM text (C-10);
- permissions are checked on the server. Hiding or disabling a button is never the only protection (C-04, FR-39).

## 2. Shared frame

### 2.1 Signed-in frame

Every page except Login uses this frame (C-01: every page except Login requires a session).

```
+--------------------------------------------------------------------------------+
| ICD     [Upload]  [Incidents]                               (o) API online     |
+--------------------------------------------------------------------------------+
|                                                                                |
|  <Page heading>                                                                |
|  <One sentence that says what this page shows>                                 |
|                                                                                |
|  <Page content>                                                                |
|                                                                                |
+--------------------------------------------------------------------------------+
```

- **Header:** the product name "ICD" on the left, then the navigation, then the API health indicator on the right.
- **Navigation:** Upload and Incidents. The current page is marked with text styling, not with colour alone.
- **Content area:** under the header, one page at a time.

### 2.2 API health indicator

The indicator reads `GET /health`. It always shows text, and the dot `(o)` is extra.

| State | Text | When |
|---|---|---|
| Checking | `Checking…` | The first request is pending |
| Online | `API online` | HTTP 200, `{"status":"ok","database":"ok"}` |
| Degraded | `API degraded: database unavailable` | HTTP 503 with `{"status":"degraded","database":"unavailable"}` |
| Unavailable | `API unavailable` | Network error, timeout, any other HTTP error, or an unreadable body. The error kind is shown on hover |

### 2.3 Shared state blocks

Every screen uses the same three blocks, so a state looks the same everywhere.

```
+- Loading ---------------------+  +- Empty -----------------------+
|  Loading incidents…           |  |  No incidents yet.            |
+-------------------------------+  +-------------------------------+

+- Error ------------------------------------------------------+
|  Could not load incidents. The ICD API did not answer.       |
|  [Retry]                                                     |
+--------------------------------------------------------------+
```

- Loading: one line naming what is loading.
- Empty: one line, and a next step where one exists.
- Error: what failed, a short reason in plain words, and a `[Retry]` button. No stack traces and no raw server text.

### 2.4 SIMULATED badge rule

Every response action is a simulation (C-13, NFR-SF-01, NFR-SF-07).

- Every response-related label, button, status and history line carries the text badge `[SIMULATED]`, or has "SIMULATED" or "simulated" in its own text.
- No screen says or suggests that a real host, IP address, account or firewall was changed. The wording is "isolated (SIMULATED)", never "isolated".
- The badge is text, so it survives a screenshot, a print and a screen reader.

### 2.5 Notation

| Mark | Meaning |
|---|---|
| `[Button]` | A button |
| `<link>` | A link |
| `( ) Option` | A choice in a list (radio button) |
| `[x]` / `[ ]` | A checkbox |
| `{field}` | A value from a contract field, for example `{risk.score}` |
| `*proposed*` | A value with no contract yet (section 6) |
| `(o)` | A status dot; the text next to it carries the meaning |

## 3. Route map

| Screen | Path | Main user action |
|---|---|---|
| Login | `/login` | Sign in |
| Upload | `/upload` | Upload a dataset file and follow its processing |
| Incident list | `/incidents` | Find an incident and open it |
| Incident detail | `/incidents/:incidentId` | Review the risk score and the related events |
| AI report panel | `/incidents/:incidentId/report` | Read the AI analysis and check its cited evidence |
| Pending decision | `/incidents/:incidentId/decision` | Decide on the simulated response, within the window if one is open |

`/` redirects to `/incidents`. An unknown path shows a "Page not found" page inside the frame.

## 4. Screens

### 4.1 Login (shell)

**Information that must be visible**

| Item | Contract field or "proposed" | Why |
|---|---|---|
| Username field | none (input) | A2.4 |
| Password field | none (input) | A2.4 |
| One generic error message | none: fixed text "Invalid username or password" | C-02: never says which field was wrong |
| Session expired notice | none: fixed text "Your session has expired" | C-03: 30 minutes idle or 8 hours absolute (A2.3) |

**Main user action.** Enter a username and a password, then press "Sign in".

**Who can use it.** Everybody. It is the only page without a session (C-01).

**Main sketch**

```
+------------------------------------------+
|  Sign in to ICD                          |
|                                          |
|  Username                                |
|  [______________________________]        |
|  Password                                |
|  [______________________________]        |
|                                          |
|  [Sign in]                               |
+------------------------------------------+
```

There is no "remember me" option and no "forgot password" link. The password is never shown, logged or stored by the browser page (A2.2).

**States**

- **Submitting:** the button reads "Signing in…" and is disabled until the server answers.
- **Error:** the generic message above the form, with the fields kept empty:

```
+------------------------------------------+
|  Sign in to ICD                          |
|  ! Invalid username or password          |
|  Username  [______________________]      |
|  Password  [______________________]      |
|  [Sign in]                               |
+------------------------------------------+
```

- **Locked out** (C-19, pending TD-8 at W6): **looks exactly like the error state**. A2.11 says that a login during a lockout is refused with the same message as any other failure, so the screen must not reveal that the account exists or is locked.
- **Session expired:** the user is sent back here with the notice "Your session has expired" above the form. After sign-in the user returns to the page they were on.
- **Loading / empty:** not applicable.

### 4.2 Upload

All upload progress and validation feedback is **(proposed, needs C1/C2 agreement)**: no upload contract exists yet (section 6, question 1).

**Information that must be visible**

| Item | Contract field or "proposed" | Why |
|---|---|---|
| File picker | none (input) | Dataset selection |
| Dataset source, from a list of registered sources | `Event.provenance.dataset_id` names it after ingestion; the list itself is *proposed* | FR-05 |
| Accepted formats and size limit | *proposed*: "<from C2>" | TM-01, TM-09, C-07, C-08, C-18 |
| Upload percentage | *proposed* | Progress feedback |
| Processing stage: Uploaded → Validating → Parsing → Correlating → Done | *proposed* | Progress feedback |
| Counts: records read, events accepted, records rejected | *proposed* | FR-03: rejected records never become Events |
| Rejection reasons, grouped with a count | *proposed* | FR-03 |
| Link to the incident list when done | none (link) | Next step |

**Main user action.** Choose a dataset source and a file, press "Upload", then follow the processing to "Done".

**Who can use it.** Security Engineer (OD-24 proposal: evaluation datasets) and System Administrator (OD-24 proposal). SOC Analyst and SOC Manager: denied (A3). The navigation entry is still shown to everybody until OD-24 decides (section 6, question 5).

**Main sketch** (processing a file)

```
+--------------------------------------------------------------------------------+
| ICD     [Upload]  [Incidents]                               (o) API online     |
+--------------------------------------------------------------------------------+
|  Upload logs                                                                   |
|  Upload a dataset file. ICD parses it, correlates the events into incidents.   |
|                                                                                |
|  Dataset source   [ <registered source>          v ]   *proposed*              |
|  File             [ Choose file ]  auth-log-week1.csv                          |
|  Accepted: <from C2>.  Maximum size: <from C2>.                                |
|  [Upload]                                                                      |
|                                                                                |
|  +- Processing --------------------------------------------------------------+ |
|  |  [x] Uploaded   [x] Validating   [>] Parsing   [ ] Correlating   [ ] Done | |
|  |                                                                           | |
|  |  Records read       12 480                                                | |
|  |  Events accepted    12 455                                                | |
|  |  Records rejected       25                                                | |
|  +---------------------------------------------------------------------------+ |
+--------------------------------------------------------------------------------+
```

**States**

- **Idle:** nothing selected. "Upload" is disabled, and the text "Choose a dataset source and a file" is shown.
- **Uploading:** "Uploading… 42%". The file picker and "Upload" are disabled.
- **Validating:** stage "Validating" is active. No counts yet.
- **Validation failed:** the file is rejected as a whole and nothing is stored:

```
+- Upload rejected ----------------------------------------------------------+
|  ! auth-log-week1.csv was not accepted. Nothing was stored.                |
|  Reason: <for example "format not accepted" or "file too large">           |
|  [Choose another file]                                                     |
+----------------------------------------------------------------------------+
```

- **Partially accepted:** processing finishes, and some records are rejected:

```
+- Done, with rejected records ----------------------------------------------+
|  Events accepted 12 455 of 12 480 records. 25 records were rejected:       |
|    missing timestamp ............ 12                                       |
|    missing event ID .............  9                                       |
|    invalid IP address ...........  4                                       |
|  <View incidents>                                                          |
+----------------------------------------------------------------------------+
```

- **Done:** all records accepted. "Done" is checked, and the link <View incidents> is shown.
- **Server error:** the shared error block (2.3) with "Upload failed. The file was not processed." and `[Retry]`.
- **Loading:** the list of registered sources is loading: shared loading block.
- **Empty:** no registered sources: "No dataset source is registered. Ask the System Administrator." (proposed).

### 4.3 Incident list

**Information that must be visible**

| Item | Contract field or "proposed" | Why |
|---|---|---|
| Incident ID | `Incident.incident_id` | FR-07 |
| Time | `Incident.first_event_at`; `last_event_at` on hover | FR-11 |
| Type | `Incident.incident_type`; "Not classified" when `null` | OD-20 |
| Risk | `Incident.risk.level` and `risk.score`; "Not scored" when `risk` is `null` | FR-18, FR-20 |
| Status | `Incident.status`, with the labels of section 5 | FR-31 |
| Analysis | `Incident.analysis_status` | OD-09 |
| "Decision needed: m:ss" badge | *proposed*: response window `deadline_at` and `server_time` (spec section 7) | FR-43, NFR-P-09 |
| Open link | `Incident.incident_id` | Navigation |

**Main user action.** Find an incident and open it. Incidents that need a decision stand out with the text badge.

**Who can use it.** SOC Analyst (decided), SOC Manager (decided, D7.2), Security Engineer (OD-24 proposal). System Administrator: denied until OD-24 (A3).

**Main sketch**

```
+--------------------------------------------------------------------------------+
| ICD     [Upload]  [Incidents]                               (o) API online     |
+--------------------------------------------------------------------------------+
|  Incidents                                                                     |
|  Correlated incidents, newest first.                                           |
|                                                                                |
|  Status [ All          v ]   Risk level [ All  v ]   *proposed filters*        |
|                                                                                |
|  Incident ID     Time               Type             Risk          Open        |
|    Status                           Analysis                                   |
|  ----------------------------------------------------------------------------  |
|  inc-2026-0003   2026-11-02 11:15   brute_force      High 74       <Open>      |
|    Awaiting Human Decision          Succeeded                                  |
|    [Decision needed: 0:42]                                                     |
|  ----------------------------------------------------------------------------  |
|  inc-2026-0002   2026-11-02 10:58   Not classified   Medium 52     <Open>      |
|    Under Analysis                   In progress                                |
|  ----------------------------------------------------------------------------  |
|  inc-2026-0001   2026-11-02 09:12   brute_force      Not scored    <Open>      |
|    New                              Not started                                |
+--------------------------------------------------------------------------------+
```

Each incident takes two lines in the sketch, to keep it narrow. On the screen the seven columns may sit on one row.

- Sorted by `first_event_at`, newest first.
- The "Decision needed" badge appears only for `status = awaiting_human_decision` with an open response window. Its time is computed from the server's `deadline_at`, as on the Pending decision screen (4.6). The badge links to `/incidents/:incidentId/decision`.
- Risk shows the level as text first, then the score. Colour is never the only signal.

**States**

- **Loading:** shared loading block "Loading incidents…".
- **Empty:** "No incidents yet. Upload a dataset to start." with a link to Upload.
- **Error:** shared error block with `[Retry]`.
- **Filtered to nothing:** "No incidents match these filters." with `[Clear filters]`.

### 4.4 Incident detail

**Information that must be visible**

| Item | Contract field or "proposed" | Why |
|---|---|---|
| Incident ID | `Incident.incident_id` | FR-07 |
| Status | `Incident.status` | FR-31 |
| Type | `Incident.incident_type`; "Not classified" when `null` | OD-20 |
| Time span | `Incident.first_event_at` to `Incident.last_event_at` | FR-11 |
| Risk score, 0 to 100 | `Incident.risk.score` | FR-18 |
| Risk level | `Incident.risk.level` | FR-20, OD-05 |
| Factor table | `Incident.risk.factors[]`: `name`, `value`, `weight`, `contribution` | FR-19, NFR-SF-05, C-17 |
| Risk configuration | `Incident.risk.config_version`, `Incident.risk.computed_at` | AS-04 |
| Risk justification | `AnalysisReport.risk_justification`; "Not determined" when `null` | FR-19 |
| Related events: link part | `Incident.events[]`: `event_id`, `role`, `link_keys` | FR-08, NFR-SF-05 |
| Related events: event part | `Event.timestamp`, `event_type`, `host`, `src_ip`, `dst_ip`, `user`, `label.status` | FR-04, OD-21 |
| Links to the AI report and the pending decision | none (links) | Navigation |

**Main user action.** Review why the events were grouped and what sets the risk score, then go to the AI report or the pending decision.

**Who can use it.** As 4.3: SOC Analyst, SOC Manager (decided); Security Engineer (OD-24 proposal); System Administrator denied until OD-24.

**Main sketch**

```
+--------------------------------------------------------------------------------+
| ICD     [Upload]  [Incidents]                               (o) API online     |
+--------------------------------------------------------------------------------+
|  <Back to incidents>                                                           |
|  Incident inc-2026-0003                                                        |
|  Status: Awaiting Human Decision                                               |
|  Type: brute_force      2026-11-02 11:15:02  to  2026-11-02 11:19:40           |
|  <AI report>   <Pending decision>                                              |
|                                                                                |
|  +- Risk ---------------------------------------------------------------------+|
|  |  High   74 / 100                                                           ||
|  |  Score computed by the risk engine; justification written by the AI.       ||
|  |                                                                            ||
|  |  Factor              Value   Weight   Contribution                         ||
|  |  severity            0.60    0.35     21.0                                 ||
|  |  flagged_share       0.75    0.20     15.0                                 ||
|  |  host_count          0.20    0.20      4.0                                 ||
|  |  attack_type_count   0.33    0.15      5.0                                 ||
|  |  privileged          not in data                                           ||
|  |                                                                            ||
|  |  Justification: {risk_justification}                                       ||
|  |  Configuration {risk.config_version}, computed {risk.computed_at}          ||
|  +----------------------------------------------------------------------------+|
|                                                                                |
|  Related events (4)                                                            |
|  Event ID  Role     Linked by  Time      Type        Host     Src IP  User     |
|  --------  -------  ---------  --------  ----------  -------  ------  -------  |
|  evt-0001  FLAGGED  (first)    11:15:02  auth_fail   host-01  ip-01   user-01  |
|  evt-0002  FLAGGED  host       11:16:40  auth_fail   host-01  ip-01   user-01  |
|  evt-0003  FLAGGED  host,user  11:18:05  auth_ok     host-01  ip-01   user-01  |
|  evt-0004  context  host       11:19:40  conn_out    host-01  ip-02   -        |
|                                                                                |
|  Dst IP and label status are further columns, cut here to keep the sketch      |
|  narrow. Context events are never treated as flagged.                          |
+--------------------------------------------------------------------------------+
```

- The factor numbers are placeholders. The real weights are pending the decision record in correlation-and-risk-design.md section 10.
- "not in data": a factor that is configured but missing from `risk.factors`, because it was excluded (correlation-and-risk-design.md section 9.3, proposed).
- **Flagged and context events differ in text**: the Role column reads `FLAGGED` or `context`. Colour may be added, but it is never the only signal (OD-02).
- "Linked by" shows `link_keys`; "(first)" marks the event that started the incident, whose `link_keys` is empty.
- Host, user and IP values may be masked tokens such as `host-01` (NFR-S-07). They are shown as plain text and never formatted as real addresses. A missing value is shown as "-".
- A cited event link from the AI report (4.5) opens this page with that event row highlighted, by a text marker `>` at the start of the row.

**States**

- **Loading:** shared loading block "Loading incident…".
- **Incident not found (HTTP 404):** "Incident inc-2026-0099 was not found." with <Back to incidents>. No Retry.
- **Error:** shared error block with `[Retry]`.
- **Risk not computed yet** (`risk` is `null`): the Risk box reads "Risk not scored yet. The risk engine computes it when the incident is created or updated." No factor table.
- **Events table empty:** "No related events to show." An incident always has at least one flagged event (contracts-v1.md section 3.2), so this state means the event details could not be read; it shows `[Retry]`.
- **Pending decision link:** shown only when `status` is `awaiting_human_decision` or `escalated`.

### 4.5 AI report panel

**Information that must be visible**

| Item | Contract field or "proposed" | Why |
|---|---|---|
| Summary | `AnalysisReport.summary` | FR-14 |
| Attack type | `AnalysisReport.attack_type`; "Not determined" when `null` | FR-14 |
| Attack sequence | `AnalysisReport.sequence[]`: `order`, `description`, `cited_event_ids`; "Not determined" when `null` | FR-14 |
| Findings, grouped by category | `AnalysisReport.findings[]`: `statement`, `category`, `cited_event_ids` | FR-15 |
| Weaknesses | `AnalysisReport.weaknesses`; "Not determined" when `null` | FR-14 |
| Impact | `AnalysisReport.impact`; "Not determined" when `null` | FR-14 |
| Recommendations, as advice | `AnalysisReport.recommendations` | C-10 |
| Uncertainty | `AnalysisReport.uncertainty` | FR-15 |
| Confidence, as a percentage | `AnalysisReport.confidence` | OD-16 |
| Footer | `AnalysisReport.generated_by`, `model_id`, `prompt_version`, `generated_at` | Traceability |
| Analysis status and attempts | `Incident.analysis_status`, `Incident.analysis_attempts` | OD-09 |

`AnalysisReport.model_self_rating` is **not** shown on the main panel. It is stored, but it never drives the 0.75 gate (OD-16).

**Main user action.** Read the analysis and check each claim against its cited events.

**Who can use it.** As 4.3: SOC Analyst, SOC Manager (decided); Security Engineer (OD-24 proposal); System Administrator denied until OD-24.

**Main sketch** (`analysis_status = succeeded`)

```
+--------------------------------------------------------------------------------+
| ICD     [Upload]  [Incidents]                               (o) API online     |
+--------------------------------------------------------------------------------+
|  <Back to incident>                                                            |
|  AI report for incident inc-2026-0003                                          |
|  [MOCK REPORT] Generated by the mock analyzer, not by an LLM.                  |
|  (This line is shown only when generated_by = mock.)                           |
|                                                                                |
|  Summary       {summary}                                                       |
|  Attack type   {attack_type}                                                   |
|  Confidence    82%  (grounding-based confidence, not the model's self-rating)  |
|                                                                                |
|  Attack sequence                                                               |
|   1. {sequence[0].description}            Evidence: <evt-0001> <evt-0002>      |
|   2. {sequence[1].description}            Evidence: <evt-0003>                 |
|                                                                                |
|  Findings                                                                      |
|   Evidence supported                                                           |
|    - {statement}                          Evidence: <evt-0003>                 |
|   Likely interpretation                                                        |
|    - None                                                                      |
|   Hypothesis                                                                   |
|    - {statement}                          Evidence: none cited                 |
|                                                                                |
|  Weaknesses       Not determined                                               |
|  Impact           {impact}                                                     |
|  Recommendations  (advice for the analyst; ICD never runs these)               |
|    - {recommendations[0]}                                                      |
|  Uncertainty      {uncertainty}                                                |
|                                                                                |
|  Generated by mock, model Not determined, prompt Not determined,               |
|  at 2026-11-02 11:20:05                                                        |
+--------------------------------------------------------------------------------+
```

- Every cited event ID is a link to the incident detail page (4.4) with that event highlighted.
- The three finding groups are always shown with their headings. An empty group reads "None".
- Recommendations are free text and are shown as advice, never as buttons (C-10). The response options are only on the Pending decision screen.
- Any `null` report field reads "Not determined" (FR-14, FR-15), never an empty box or a guess. `model_id` and `prompt_version` are `null` for the mock.
- The risk score is not in the report (OD-04). The incident detail page (4.4) shows `risk.score` next to `risk_justification`.

**States** (by `Incident.analysis_status`)

- **`not_started`:** "Analysis has not started."
- **`in_progress`:** shared loading block "Analysis in progress…".
- **`failed`:**

```
+- Analysis failed ----------------------------------------------------------+
|  ! The AI analysis failed after 2 attempts.  ({analysis_attempts})         |
|  No response window is opened for a failed analysis.                       |
|  [Re-analyze]                                                              |
+----------------------------------------------------------------------------+
```

  The incident stays in Under Analysis (OD-09). "Re-analyze" is the manual retry after the automatic one (spec section 2).
- **`succeeded`:** the main sketch.
- **Confidence below 0.75:** a note under Confidence: "Below the confidence threshold: no automatic response window" (OD-16, spec section 5).
- **Loading:** shared loading block "Loading report…". **Error:** shared error block with `[Retry]`.

### 4.6 Pending decision

The response window fields (`window_id`, `started_at`, `deadline_at`, `server_time`, `recommended_scenario_id`, status) come from C5's response-window record. It is **not** a shared contract (contracts-v1.md section 3.5), and its read and push format is **(proposed, needs C1/C5 agreement)** (spec section 7; section 6, question 2).

**Information that must be visible**

| Item | Contract field or "proposed" | Why |
|---|---|---|
| Countdown `m:ss` | *proposed*: window `deadline_at` and `server_time` | FR-43, NFR-P-09 |
| Reminder at 30 seconds remaining | *proposed*: `response_window.reminder` event | OD-19 (proposed) |
| Simulated isolation status | *proposed*: isolation flag of the freeze (spec section 2); host from `ResponseAction.target.host` | OD-17, NFR-SF-07 |
| Recommended scenario | *proposed*: window `recommended_scenario_id`, or `ResponseAction.scenario_id` with `state = proposed` | FR-43, FR-25, C-10 |
| Scenario description | Catalogue v0 text, spec section 9 | OD-20 |
| The three options | Spec section 8 | FR-34, FR-28 |
| Optional comment | `ResponseAction.comment` | FR-28 |
| Decision record | `ResponseAction.decided_by`, `decided_at`, `scenario_id`, `comment`; decision type *proposed* | FR-28 |
| Incident status | `Incident.status` | FR-31 |

**Main user action.** Choose one of the three options, confirm, and submit, before `deadline_at` when a window is open.

**Who can use it.** Only the SOC Analyst can submit (D1.2). SOC Manager: sees the page read-only (OD-24 proposal: reviews but makes no response decisions). Security Engineer: read-only (OD-24 proposal for viewing incidents). System Administrator: denied until OD-24 (A3). The server checks the role on every submit (FR-39).

**Main sketch** (freeze with an open window)

```
+--------------------------------------------------------------------------------+
| ICD     [Upload]  [Incidents]                               (o) API online     |
+--------------------------------------------------------------------------------+
|  <Back to incident>                                                            |
|  Pending decision for incident inc-2026-0003                                   |
|  Status: Awaiting Human Decision                                               |
|                                                                                |
|  +- Response window -------------------------------------------------------+   |
|  |                                                                         |   |
|  |        0:42        time left to decide                                  |   |
|  |                                                                         |   |
|  |  Deadline set by the server: 2026-11-02 11:21:05. If no decision is     |   |
|  |  recorded by then, the system selects a scenario (SIMULATED).           |   |
|  +-------------------------------------------------------------------------+   |
|                                                                                |
|  Host host-01: isolated (SIMULATED)                                            |
|                                                                                |
|  +- Recommended response [SIMULATED] --------------------------------------+   |
|  |  S2  Isolate the host and block the source IP.                          |   |
|  |  Chosen by the catalogue lookup, not by the AI.                         |   |
|  +-------------------------------------------------------------------------+   |
|                                                                                |
|  Your decision                                                                 |
|  ( ) Approve recommended action (S2, SIMULATED)                                |
|  ( ) Reject and release simulated isolation                                    |
|  ( ) Select another scenario (SIMULATED):                                      |
|        ( ) S1  Keep the host isolated and flag it for investigation            |
|        ( ) S2  Isolate the host and block the source IP                        |
|        ( ) S3  Isolate the host and disable the involved account               |
|        ( ) S4  Release isolation and raise monitoring                          |
|                                                                                |
|  Comment (optional)                                                            |
|  [________________________________________________________________]            |
|                                                                                |
|  [Review decision]                                                             |
+--------------------------------------------------------------------------------+
```

- The countdown shows `remaining = deadline_at − (client_now + offset)`, with the offset taken from the server's `server_time` (spec section 7). The browser never starts its own 60-second timer, and a page refresh shows the same window: it never restarts at 1:00 (NFR-P-09).
- The options are in the order of spec section 8. S4 is listed only under "Select another scenario": it is never recommended or selected automatically (spec section 9).
- "Reject" on an incident **without** a freeze records the rejection only; there is no isolation to release (spec section 8). The option then reads "Reject the recommendation".

**Confirmation step** (after "Review decision")

```
+- Confirm your decision ----------------------------------------------------+
|  Incident inc-2026-0003                                                    |
|  Decision: Approve recommended action                                      |
|  Scenario: S2  Isolate the host and block the source IP  [SIMULATED]       |
|  Comment:  (none)                                                          |
|  No real system is changed. The action is simulated and audited.           |
|                                                                            |
|  0:31 left        [Back]  [Submit decision]                                |
+----------------------------------------------------------------------------+
```

The countdown keeps running in the confirmation step. "Back" comes before "Submit decision" (section 5).

**States**

- **Freeze with an open window:** the main sketch.
- **Reminder (30 seconds left, OD-19, proposed):** the countdown box gains the text line "30 seconds left". The text, not only the style, carries the reminder.
- **No window** (High with confidence < 0.75, Medium or Low; spec section 5): the countdown box is replaced by "No response window. No automatic action will run." The isolation line is not shown. The three options stay available (FR-25).
- **No matching scenario** (spec section 6): the Recommended box reads "No catalogue scenario matches this incident." "Approve" is disabled with the reason next to it: "No recommended scenario". "Reject" and "Select another scenario" stay available.
- **Decided:**

```
+- Decision recorded --------------------------------------------------------+
|  By {decided_by} at {decided_at}                                           |
|  Decision: Approve recommended action   *proposed: decision type*          |
|  Scenario: S2  [SIMULATED]              Comment: {comment}                 |
|  Status: Response in Progress                                              |
+----------------------------------------------------------------------------+
```

- **Window expired, scenario selected** (spec section 10, case 3): "Window expired at 2026-11-02 11:21:05. The system selected S2 (SIMULATED)." The options are gone.
- **Window expired, no match** (spec section 10, case 1): "Window expired at 2026-11-02 11:21:05. No scenario matched: escalated to the SOC Manager."
- **Decision refused, window expired** (HTTP 409, spec section 10, case 4): "Your decision was not recorded: the window expired at 11:21:05. The system path applies." The page then shows the expired state.
- **Not authorized** (HTTP 403, spec section 10, case 6): "You are not allowed to make response decisions. Nothing was executed."
- **Read-only** (any role other than SOC Analyst): the countdown and the recommendation are shown; the options, the comment and the buttons are not. A line reads "Only a SOC Analyst can decide."
- **Live connection lost:** a line above the countdown: "Reconnecting… the time shown is still calculated from the server deadline." The countdown keeps going from the stored `deadline_at`.
- **Loading:** shared loading block "Loading response window…". **Error:** shared error block with `[Retry]`.

## 5. Consistency rules

**Status labels** (`Incident.status`, spec section 2):

| Value | Label |
|---|---|
| `new` | New |
| `under_analysis` | Under Analysis |
| `awaiting_human_decision` | Awaiting Human Decision |
| `response_in_progress` | Response in Progress |
| `escalated` | Escalated |
| `resolved` | Resolved |
| `closed` | Closed |

**Risk level labels** (`risk.level`): `low` → Low, `medium` → Medium, `high` → High. The score is shown after the level, for example "High 74". The level is always text; colour is extra.

**Analysis status labels** (`analysis_status`): `not_started` → Not started, `in_progress` → In progress, `succeeded` → Succeeded, `failed` → Failed.

**Finding category labels** (`findings[].category`): `evidence_supported` → Evidence supported, `likely_interpretation` → Likely interpretation, `hypothesis` → Hypothesis.

**Dates.** The contracts carry ISO 8601 UTC. The screen shows local time as `YYYY-MM-DD HH:MM:SS` (lists may drop the seconds). Hovering shows the UTC value, for example `2026-11-02T09:15:30.250Z`.

**Missing values.**
- A `null` report field reads "Not determined" (FR-14).
- `incident_type = null` reads "Not classified", and `risk = null` reads "Not scored".
- A missing event field reads "-".

**Masked values.** Host, user and IP values may be tokens such as `host-01` (NFR-S-07). They are shown as given, as plain text.

**Back links.**

| Screen | Back link goes to |
|---|---|
| Incident detail | Incident list |
| AI report panel | Incident detail |
| Pending decision | Incident detail |
| Upload | none: it is a top-level page |

**Button order.** The safe or secondary action comes first and the main action last: `[Back]  [Submit decision]`. A destructive or irreversible action always has a confirmation step. There is one main button per form.

**SIMULATED.** As 2.4, on every response label.

## 6. Open questions

| # | Question | Proposed default | Who decides |
|---|---|---|---|
| 1 | Upload contract: endpoint, processing stages and counts, rejection reasons, accepted formats and size limit | Stages Uploaded → Validating → Parsing → Correlating → Done, with records read, events accepted, records rejected and grouped reasons | C1, C2 |
| 2 | REST read of the open response window after a page refresh, and its fields | Same fields as `response_window.opened`: `incident_id`, `window_id`, `started_at`, `deadline_at`, `server_time`, `recommended_scenario_id`, plus `status` | C1, C5 |
| 3 | Does the incident list response carry the window deadline, or does the dashboard make a separate call per incident? | The list carries `deadline_at` and `server_time` for incidents with an open window | C1, C5 |
| 4 | Where do the event details for 4.4 come from: embedded in the incident response, or a separate events endpoint? | A separate endpoint that returns the incident's Events, paginated | C1, C3 |
| 5 | Who sees the Upload screen? | OD-24 proposal: Security Engineer and System Administrator; the others do not see the nav entry | C5 |
| 6 | Are risk factor names shown raw (`flagged_share`) or with labels? | Labels from C3's configuration, with the raw name on hover | C3 |
| 7 | Where does the decided state get the decision type (approve, reject, select)? `ResponseAction` has no such field, and a reject creates no `ResponseAction` | From the `decision.recorded` audit record (`AuditRecord.details`), or a decision type on the window record | C5, C3 |
| 8 | Where does the dashboard read the simulated isolation flag and its host? | On the response-window record, with the host from the proposed `ResponseAction.target.host` | C5, C1 |
| 9 | How does the dashboard know which factors are configured, to show "not in data" for an excluded one? | The API returns the configured factor names with the incident, or a configuration endpoint | C3, C1 |
| 10 | Does a session expiry return the user to the page they were on after sign-in? | Yes, to the same path | C5 |

## 7. Traceability

| Requirement or decision | Screen |
|---|---|
| C-01 (every page except Login needs a session) | 2.1, 4.1 |
| C-02 (one generic login error) | 4.1 |
| C-03 (session expiry) | 4.1 |
| C-19, TD-8 (lockout) | 4.1 |
| C-04, FR-39 (server-side permissions) | 1, 4.2, 4.6 |
| C-07, C-08, C-18, TM-01, TM-09 (upload limits) | 4.2 |
| FR-03, FR-05 (rejected records, provenance) | 4.2 |
| FR-07, FR-08, FR-11 (incident, linked events, time span) | 4.3, 4.4 |
| FR-14, FR-15 (report sections, finding categories, "Not determined") | 4.5, 5 |
| FR-18, FR-19, FR-20, OD-04, OD-05 (deterministic score, factors, level) | 4.3, 4.4 |
| NFR-SF-05, C-17 (why events were grouped, what sets the risk) | 4.4 |
| OD-02 (context events never treated as flagged) | 4.4 |
| OD-09 (analysis failure, Re-analyze) | 4.5 |
| OD-16 (confidence, not the model's self-rating; 0.75 threshold) | 4.5 |
| C-10 (recommendations are advice; the catalogue lookup picks the scenario) | 4.5, 4.6 |
| FR-31, TD-11 (lifecycle states and labels) | 4.3, 4.4, 5 |
| FR-43, NFR-P-09 (server-owned 60-second window) | 1, 4.3, 4.6 |
| OD-17 (one window per incident, simulated isolation) | 4.6 |
| OD-19 (30-second reminder, proposed) | 4.6 |
| OD-20, FR-44 (catalogue S1 to S4; S4 never automatic) | 4.6 |
| FR-25 (options without a window) | 4.6 |
| FR-28, FR-34 (three options, decision record) | 4.6 |
| Spec section 10, cases 1, 3, 4, 6 | 4.6 |
| NFR-SF-01, NFR-SF-07, C-13 (SIMULATED on every response label) | 2.4, 4.6 |
| NFR-S-07 (masked tokens) | 4.4, 5 |
| D1.2, D7.2, OD-24, A3 (who can use each screen) | 4.1 to 4.6 |
