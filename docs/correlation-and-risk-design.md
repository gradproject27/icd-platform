# Correlation and risk score design

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **Owner** | C3, Detection & Correlation |
| **Task** | T1-08 (Week 1). Implemented in Week 2 by T2-08 (correlation engine v0) and T2-09 (risk score) |
| **Status** | Draft. Items marked **(proposed, needs team agreement)** are C3 design choices, not decisions. Section 15 lists every one of them. Q1 to Q9 were answered by the team on 28 Oct 2026 (section 15); the correlation engine v0 implements them in `backend/app/correlation/` |
| **Sources** | Ratified decision register (OD-xx, TD-xx, D2); approved requirements (FR-xx, NFR-xx); acceptance scenarios (AS-xx); constraints (CON-xx, C-xx); data requirements (DR-xx); contracts v1 (T1-07, [contracts-v1.md](contracts-v1.md)); [response workflow specification](response-workflow-spec.md) |

## 1. Scope and rules

This document specifies how ICD turns events into incidents and how it computes the deterministic risk score of an incident. C3 implements it in Week 2: the correlation engine v0 in T2-08 and the risk score in T2-09.

It does not change migrations, dependencies or the shared contracts. The correlation engine v0 (T2-08) implements sections 3 to 8 in `backend/app/correlation/`, with the configuration of section 13; the risk score (sections 9 to 12) is still planned.

Each rule cites its source. Items marked **(proposed, needs team agreement)** are not decisions until the team agrees them.

**Rule 1: no detection layer (D2).** ICD has no detection layer. Correlation never decides that an event is malicious. Whether an event is flagged, unflagged or unlabelled comes only from the dataset label (FR-40, OD-21). Correlation groups events that the dataset has already flagged, and attaches related events as context. This document therefore uses the words **flagged**, **unflagged**, **unlabelled** and **context**, and does not call events or incidents malicious.

**Rule 2: the risk score is code (OD-04, FR-19).** The numeric risk score is computed by C3 code from configured weights. The LLM never computes or changes it. The LLM writes only the risk justification (`AnalysisReport.risk_justification`), which explains the score it is given.

**Rule 3: deterministic (AS-04).** The same input and the same configuration always give the same incidents, links, types and scores.

Terms:

| Term | Meaning |
|---|---|
| flagged event | An event whose dataset label has `label.status = flagged` (OD-21) |
| unflagged event | An event whose dataset label has `label.status = unflagged` |
| unlabelled event | An event with no dataset label, `label.status = unlabelled`. Never inferred (OD-21) |
| context event | An unflagged or unlabelled event attached to an incident, `role = context` (OD-02) |
| key value | One normalized value of a relatedness key, for example `host = ws-17` (section 3) |
| group | A set of flagged events found related by the grouping algorithm (section 5) |

## 2. Inputs

Correlation reads `Event` records (contracts v1) after the intake layer (C2) has parsed and normalized them (FR-40).

| Event field | Used for | Source |
|---|---|---|
| `event_id` | Identity; deterministic tie-breaking | FR-03 |
| `timestamp` | Event time: the window and ordering (section 4) | OD-15, TD-12 |
| `label.status` | Split into flagged events and context candidates | FR-40, OD-21 |
| `label.attack_type` | Incident type (section 8); severity and attack-type factors (section 9) | OD-21, OD-04 |
| `host` | Key `host` | OD-02 |
| `src_ip`, `dst_ip` | Key `ip_pair` | OD-02 |
| `user` | Key `user` | OD-02 |
| `privileged_user` | Not used by the risk method of 29 Oct 2026 (section 9); kept in the contract | OD-04 |

Rules:

- `label.status` is one of `flagged`, `unflagged` or `unlabelled`. **Unlabelled events are treated exactly like unflagged events**: they can only be context, and no label is ever inferred for them (OD-21).
- **Columns produced by another correlation engine are never used** as keys or features (CON-20). Only raw event fields are used. C2 keeps such columns out of `extra_fields` (contracts v1, `Event.extra_fields`).
- `ingested_at` (parse time, TD-12) is not used for grouping. The dataset is uploaded in batches, so parse time says nothing about when the activity happened.

## 3. Relatedness keys

Two events can be related only through a shared **key value** (OD-02). The list of keys lives in configuration (section 13). The keys match `LinkKey` in contracts v1.

| Key | Built from | Normalization (proposed, needs team agreement) | Source |
|---|---|---|---|
| `host` | `Event.host` | Trimmed, lower-case | OD-02 |
| `ip_pair` | `Event.src_ip` and `Event.dst_ip`, both present | Unordered pair, so A→B and B→A give the same key value. IP addresses in canonical text form | OD-02 |
| `user` | `Event.user` | Trimmed, case-folded | OD-02 |

Rules:

- **A null field produces no key** (OD-02). An event with only `src_ip` produces no `ip_pair` key. An event with no key at all can never be related to another event.
- **Key denylist (proposed, needs team agreement).** A configured denylist `key_denylist` can exclude shared values that would otherwise link almost everything. It is **empty by default**. Examples of values a team might add after looking at the data: a broadcast address such as `255.255.255.255` inside an `ip_pair`, a generic account such as `system` or `anonymous`, a shared jump host. A denylisted value produces no key.
- **Event type is not a linking key in v0 (proposed, needs team agreement).** The task sheet lists event type and time as possible signals. In v0, time is used through the window (section 4). `Event.event_type` is not a key, because a multi-stage attack changes event type between stages (for example a scan, then failed logins, then a successful login), and OD-02 links on entities, not on activity type. The type of activity enters the design through `label.attack_type` instead, which sets the incident type (section 8) and the severity factor (section 9).

## 4. Time window and update rule

**Window (OD-15).** Correlation uses a **15-minute gap window**. 15 minutes is a configuration default (`window_minutes`), tuned in W11.

**Direct relation.** Two flagged events are **directly related** when:

1. they share at least one key value (section 3), and
2. their timestamps differ by no more than the window in force for that key value: 15 minutes, `|t₁ − t₂| ≤ 15 min`, or 30 minutes while the key value's chain is escalated (adaptive memory, below). The boundary is inclusive (team, 28 Oct).

With adaptive memory, the relation is evaluated along each key value's chain of flagged events in time order (section 5.1), because whether a value is escalated depends on the events before it.

**Time means event time** (`Event.timestamp`), never upload or parse time (TD-12 defines arrival as parse time; arrival is not used for grouping).

**Chaining.** Because it is a gap window, not a fixed window, relations chain: events are in the same group when a path of direct relations connects them.

| Event | Time | Host | Direct relations |
|---|---|---|---|
| A | 10:00 | `ws-17` | A–B (10 min) |
| B | 10:10 | `ws-17` | A–B, B–C (10 min each) |
| C | 10:20 | `ws-17` | B–C (10 min) |

```
10:00      10:10      10:20
  A ──10m── B ──10m── C        one incident {A, B, C}
  └────────20m────────┘        A and C are not directly related (20 min > 15 min)
```

A and C are 20 minutes apart, so they are not directly related, but both are related to B, so A, B and C form one incident.

**Update rule (OD-15).** An incident accepts new events until two windows (30 minutes of event time, `update_idle_windows = 2`) pass with no new event for it.

An incident is **open for updates** exactly when both hold:

| # | Condition | Source |
|---|---|---|
| 1 | `W − incident.last_event_at < 30 min`, where `W` is the latest event time seen in the input so far (section 7.3) | OD-15 |
| 2 | `incident.status ≠ closed`. A closed incident is never reopened | OD-14 |

An incident that is not open for updates keeps its events. A later related flagged event starts a new incident instead.

**Adaptive memory (team decision, 28 Oct 2026; amends OD-15 for linking).** The window in force for a key value depends on how far its current chain has gone in the kill chain (section 8):

| Rule | Value | Config key |
|---|---|---|
| Base window | 15 min, inclusive | `window_minutes` |
| Escalated window, while the key value's current chain has reached stage 2 (exploitation) or later | 30 min, inclusive | `escalated_window_minutes`, `escalation_min_stage` |
| The memory ends | when the chain breaks: a gap longer than the window in force | |
| Context attachment | always the base window | |

The escalated window equals the OD-15 update horizon (two windows), so an incident that is still open for updates can still grow. Reconnaissance-only activity keeps the 15-minute window, so scanning noise is not chained more widely. The decision log entry for OD-15 should record this amendment; both windows are tuned in W11.

## 5. Union-find grouping

Grouping finds the connected components of the "directly related" relation over flagged events (OD-02). It uses a union-find (disjoint-set) structure.

**What is compared.** Only flagged events are compared with each other. Two flagged events are compared only when they share a key value and lie within the window. Unflagged and unlabelled events never take part in grouping (section 6).

### 5.1 Steps

1. **Split** the input events into flagged events (`label.status = flagged`) and context candidates (`unflagged` and `unlabelled`).
2. **Sort** the flagged events by `(timestamp, event_id)`. The tie-break on `event_id` makes the order, and so the result, deterministic.
3. **Make a set** for every flagged event (union-find `make_set`).
4. **Scan** the sorted flagged events. Keep a map `last[key value] → the last flagged event seen with that key value`. For each flagged event `e`, for each of its key values `v`:
   1. if `last[v]` exists and `e.timestamp − last[v].timestamp ≤` the window in force for `v` (section 4, adaptive memory), **union** `e` with `last[v]`; otherwise the memory of `v` ends;
   2. set `last[v] = e`, and mark `v` escalated if `e` is at stage 2 or later.
5. **Collect groups.** Each union-find set is one group of flagged events.
6. **Attach context events** (section 6), then **build incidents** (section 7).

### 5.2 Pseudocode

```text
function group_flagged(events, config):
    flagged  = [e for e in events if e.label.status == "flagged"]
    context  = [e for e in events if e.label.status in ("unflagged", "unlabelled")]
    flagged  = sort(flagged, by = (e.timestamp, e.event_id))

    uf   = UnionFind()                # path compression + union by rank
    last = {}                         # key value -> last flagged event with that value
    escalated = {}                    # key value -> its current chain reached stage 2+
    for e in flagged:
        uf.make_set(e)
        for v in key_values(e, config):              # e.g. ("host", "ws-17")
            p = last.get(v)
            window = config.escalated_window if escalated.get(v) else config.window
            if p is not None and e.timestamp - p.timestamp <= window:
                uf.union(e, p)        # record v as a link key of e (section 7.1)
            else:
                escalated[v] = False  # the chain breaks, the memory ends
            if stage(e.label.attack_type) >= config.escalation_min_stage:
                escalated[v] = True
            last[v] = e
    return uf.sets(), context

function key_values(e, config):        # keys and denylist come from config
    values = []
    if "host" in keys and e.host is not null:
        values.add(("host", normalize_host(e.host)))
    if "ip_pair" in keys and e.src_ip is not null and e.dst_ip is not null:
        values.add(("ip_pair", unordered_pair(e.src_ip, e.dst_ip)))
    if "user" in keys and e.user is not null:
        values.add(("user", casefold(trim(e.user))))
    return [v for v in values if v not in denylist]
```

With path compression and union by rank, the scan costs near-linear time, `O(n · k · α(n))` for `n` flagged events and `k ≤ 3` keys, plus `O(n log n)` for the sort.

### 5.3 Why comparing only with the last event per key value is enough

Comparing every pair of flagged events would cost `O(n²)`. Comparing only with the last event for each key value gives **the same groups**, because of the sorted order and the gap window. The argument below uses one window; with adaptive memory it holds per key value, because the window in force is fixed for each consecutive pair of that value's chain, and the relation is defined on those consecutive pairs (section 4):

- **No false unions.** Every union in step 4 joins two events that share a key value and lie within the window, so every union is a direct relation.
- **No missed groups.** Take any direct relation between an earlier event `p` and a later event `e` sharing key value `v`, with `e.timestamp − p.timestamp ≤ window`. When `e` is processed, `last[v]` is the most recent event with value `v` before `e`, so `p.timestamp ≤ last[v].timestamp ≤ e.timestamp`. Then `last[v]` is also within the window of `e`, and they are unioned. All events with value `v` between `p` and `last[v]` lie inside `[p.timestamp, e.timestamp]`, so the gap between consecutive ones is at most the window, and each consecutive pair was unioned when the later one was processed. So `p`, `last[v]` and `e` end in the same set.

The sets are therefore exactly the connected components of the direct relation, the same as an all-pairs comparison would give.

### 5.4 How groups merge and stay separate

| Situation | Result | Source |
|---|---|---|
| Two flagged events share a key value within the window | Same group | OD-02, OD-15 |
| A chain of direct relations connects two events | Same group, even if they are more than 15 minutes apart (section 4) | OD-15 |
| A flagged event shares a key value with an event of group X and another key value (or the same one) with an event of group Y, both within the window | It unions X and Y into one group | OD-02 |
| Two flagged events share no key value, or every shared key value is more than 15 minutes apart with no chain between them | Separate groups | OD-02 |

## 6. Context events

Context events show the activity around flagged events. They come from unflagged and unlabelled events only (OD-02, FR-40).

**Attachment rule (OD-02).** An unflagged or unlabelled event `c` that shares a key value with a flagged event `f` of a group, with `|c.timestamp − f.timestamp| ≤ window`, is attached to that group as a context event (`role = context`). A context event may come before or after the flagged event.

| Rule | Status | Source |
|---|---|---|
| Context events **never merge groups**. A context event that matches two groups does not union them | Team, 28 Oct (Q5) | OD-02 |
| If a context event matches several groups, it is attached to the group of the flagged event **nearest in time** to it. Ties go to the **earliest group**: the group whose first flagged event comes first by `(timestamp, event_id)`. Context events do not count here, so the order of groups does not depend on what is attached | Team, 28 Oct (Q6) | OD-02 |
| A context event is attached to at most one group | Follows from the rule above | OD-02 |
| A context event is never marked or counted as flagged. It never changes what the dataset label says about the incident ("never treated as malicious", contracts v1 `EventRole`) | Ratified | OD-02, OD-21 |
| Context events alone never create an incident. Every incident has at least one flagged event (contracts v1 validator) | Ratified | OD-02 |
| A context event that matches no group stays in the event store, visible in the event list, outside any incident | Ratified | FR-40 |
| In the evidence package, context events come after all flagged events | Ratified | OD-03 |

**Why context events never merge groups.** A busy server, a shared account or a gateway appears in many unflagged events. If context events could union groups, one such host would chain unrelated incidents into one large incident. Only flagged events, whose labels come from the dataset, decide which groups exist.

**Context events never change the risk score.** The score uses flagged events only (section 9.1), so attaching context can neither raise nor lower it (tested).

**Implementation note.** For each key value, keep the flagged events with that value sorted by time. For a context candidate, a binary search per key value finds the nearest flagged event within the window. This keeps attachment at `O(m · k · log n)` for `m` context candidates.

## 7. Incident building

### 7.1 New incidents

| Rule | Status | Source |
|---|---|---|
| Each new group becomes **one incident** in state `New` (transition T01 of the response workflow spec) | Ratified | FR-07, FR-11, TD-11 |
| The incident has one `IncidentEventLink` per event, flagged and context | Ratified | FR-08 |
| Each link stores `role` (`flagged` or `context`) and `link_keys`, the keys that linked the event, so the dashboard can show why events were grouped. The first flagged event in sorted order started the incident and has empty `link_keys`. Any other flagged event lists the keys of the unions it took part in as the later event; an event that started a chain which a later event merged into the group lists the keys it was linked by as the earlier event, so only the starting event has empty `link_keys` (contract rule). A context event lists the keys it shares with the flagged event it was attached to | Ratified (`link_keys`); key rule proposed, needs team agreement | NFR-SF-05 |
| `first_event_at` and `last_event_at` are the earliest and latest `timestamp` among all linked events | Ratified (contracts v1) | FR-08 |
| **One consolidated alert per incident**, raised when the incident is created | Ratified | FR-12 |
| A flagged event that matches no other flagged event becomes an **incident of one event**, so no flagged activity is lost | Proposed, needs team agreement | FR-07 |
| Audit record `incident.created` for each new incident | Proposed in contracts v1 | FR-07 |

**Effect of incidents of one event.** Isolated flagged events raise the incident count. Every report of the incident count therefore also reports alert compression (flagged events per incident, section 14), so the effect is visible.

### 7.2 Updates to existing incidents

A new flagged event that is directly related (section 4) to an event of an incident that is **open for updates** joins that incident (FR-09):

| Effect | Source |
|---|---|
| The event is linked with `role = flagged` and its `link_keys` | FR-08, FR-09 |
| Any new events of the same group, and context events attached to it, are linked as well | FR-09, OD-02 |
| `updated_at` and `last_event_at` change | FR-09 |
| The risk score is recomputed (section 9) | FR-18 |
| Re-analysis is requested | FR-16 |
| **No second alert** is raised | FR-10 |
| Audit record `incident.updated` (proposed in contracts v1) | FR-09 |
| The lifecycle effect follows the response workflow spec (section 2 and transition T14), not this document | FR-31 |

**One new event matches two open incidents (proposed, needs team agreement).** In the MVP the existing incidents are **not merged**. The event, and the rest of its new group, join the incident created first (earliest `created_at`, then smallest `incident_id`). The `incident.updated` audit record notes the ID of the other incident. Merging incidents that have already been analysed would invalidate their reports, response windows and audit history.

### 7.3 Processing order across uploads

The dataset is uploaded in batches. Each correlation run:

1. loads the flagged events of every incident that may still be open for updates, as seeds;
2. runs sections 5 and 6 over the seeds plus the new events, in `(timestamp, event_id)` order;
3. evaluates the update rule (section 4) with `W` equal to the latest event time seen so far, in earlier runs and earlier in the current sorted pass;
4. links groups that contain seeds of an open incident to that incident, and turns the other groups into new incidents.

Results are deterministic for the same uploads in the same order (AS-04). If two batches overlap in event time, an incident that a later batch would have extended can already be closed for updates, so the upload order can change the result. This is a consequence of the idle rule of OD-15, and is reported with the evaluation.

## 8. Incident type

C5's scenario lookup reads `Incident.incident_type` (OD-20; response workflow spec, section 9).

**v0 rule (team decision Q9, 28 Oct 2026): the most advanced kill-chain stage reached.**

| Step | Rule |
|---|---|
| 1 | Take `label.attack_type` of the incident's **flagged** events. Context events are not counted |
| 2 | Map each attack type to its kill-chain stage with the configured table. An attack type missing from the table is stage 0 |
| 3 | The incident type is the attack type at the **highest stage** reached |
| 4 | Ties at that stage go to the **most frequent** attack type, then to **alphabetical order** |
| 5 | If no flagged event has an attack type, `incident_type = null` ("not classified") |

**Kill-chain stages (provisional, C3 proposal, needs team agreement).** Five stages after the Lockheed Martin kill chain, mapped to the UNSW-NB15 categories:

| Stage | Name | Attack types |
|---|---|---|
| 1 | reconnaissance | Reconnaissance, Analysis, Fuzzers |
| 2 | exploitation | Generic, Exploits |
| 3 | installation | Shellcode, Backdoors |
| 4 | propagation | Worms |
| 5 | actions on objectives | DoS |

The same stages drive the adaptive window (section 4) and can drive the progression factor of the risk score (T2-09).

The type is recomputed whenever the incident is updated. The list of attack types comes from C2's label mapping (T1-06). C5 fills its lookup table (response workflow spec, section 9) from that list.

## 9. Risk score

**Method: team decision of 29 Oct 2026.** It replaces the weighted factor sum proposed in Week 1 (sections 9 and 10 of earlier versions). The score is still computed in code from configured values (OD-04, OD-05); the LLM writes only the justification (FR-19). Code: `backend/app/correlation/risk.py`; values: `backend/app/correlation/risk.toml`.

### 9.1 Formula

| Step | Formula | Meaning |
|---|---|---|
| 1. Event strength | `q_i = S_i · C_i · O_i · D_i` | Every **flagged** event of the incident. Context events never count |
| 2. Evidence groups | `q_g = max q_i` per `(technique, entity)` | Repeated alerts and one source scanning many targets count once (anti-flooding) |
| 3. Likelihood | `L = 1 − Π_g (1 − q_g)` | Noisy-OR across groups |
| 4. Impact | `I = max` asset impact over the incident's assets | NIST FIPS 199 high water mark |
| 5. Score | `score = round_half_up(100 · L · I)` | Integer 0 to 100 (FR-18); level from section 11 |

### 9.2 The terms

| Term | Rule (team answers, 29 Oct 2026) | Config |
|---|---|---|
| `S_i` severity | 1) the source's own severity in `extra_fields["severity"]` when listed (Precinct6 product severity: critical 1.0, high 0.8, medium 0.5, low 0.3, informational/info 0.1); 2) else from the kill-chain stage of `label.attack_type` (section 8): stage 1 → 0.3, 2 → 0.6, 3 → 0.9, 4 → 0.9, 5 (DoS) → 0.7; 3) else 0.5 with flag `severity_default`. No model learns severity: UNSW-NB15 and CIC-IDS2017 have no severity column, and Precinct6's is read directly (Q8) | `[severity]` |
| `C_i` event confidence | How far the dataset's flagged label is trusted, per `provenance.dataset_id`: 1.0 by default (UNSW-NB15 labels are lab ground truth), Precinct6 0.8 (labels come from WitFoo's own correlation engine). Provisional. **Never from the LLM** (OD-04): the score is computed before the analysis and sent to it (section 9.4), and the dataset's own "is this alert true" columns are CON-20 | `[confidence]` |
| `O_i` outcome | From `extra_fields["action"]`: success 1.0, failed or blocked 0.5, no value or an unlisted value = unknown 1.0 with flag `outcome_unknown`. A blocked attack never scores 0. UNSW-NB15 has no outcome field, so its events are unknown. Value lists provisional until C2 profiles Precinct6 actions | `[outcome]` |
| `D_i` decay | `0.5 ^ ((W − t_i) / T½)`, `T½ = 24 h`. `W` is the **dataset clock**: the latest event time in the input, the same `W` as section 7.3. Never the wall clock: the datasets are historical (2015 to 2024), so the wall clock would make every `D` almost 0. An event after `W` is not boosted. Successful compromise (Backdoors, Backdoor, Worms) has `D = 1` | `[decay]` |
| technique | `label.attack_type`, or `unknown` | |
| entity | Source side: `src_ip`, else `user` (trimmed, case-folded), else `host` (trimmed, lower-cased), else `none`. One entity per event, so no event counts twice. A target-side entity would undo the anti-scan goal (one source on 20 targets would score 100) | |
| asset | The flagged event's `host`, else its `dst_ip` (UNSW-NB15 flows have no host) | |
| `I` impact | NIST FIPS 199 level of each asset from the asset table: low 0.33, moderate 0.67, high 1.0; the incident takes the max. An asset with no level, or an incident with no asset, counts as **1.0** with flag `asset_unknown` (CVSS v4.0: Not Defined = High, the worst case). The production table is empty, because the datasets' hosts are anonymised; the fixture's placeholder levels are in `fixtures/correlation/assets.toml` | `[impact]`, `[assets]` |

Deferred until a test asks for them (team, 29 Oct): progression and source bonuses (`b_prog`, `b_src`), the confirmed-compromise override, time buckets and `ρ`, `I_min`.

**Properties checked by tests** (`backend/tests/correlation/test_risk_score.py`): a scan from one source to 5, 20 or 50 targets scores the same as to one target; 100 repeats of one alert score the same as one; with a fixed `W`, adding a flagged event never lowers the score; context events never change it; a backdoor outscores a 50-host reconnaissance scan; an unknown asset never scores below a known one; same input, same output, in any order (AS-04).

**Sensitivity** (same test file): scaling each group of values by ±20% (the stage severities, the half-life, the FIPS 199 levels, the unknown-asset impact) moves at most one fixture incident to another level (F, Medium → Low, at −20% severity or −20% unknown impact), and attack A stays High in every case.

**Known properties.** (1) `W` moves forward when later events arrive, so an older incident's score can fall slightly as the batch grows; that is what decay is for. (2) Noisy-OR saturates: several strong groups give `L` close to 1. (3) Impact multiplies: a confirmed backdoor on a Low workstation scores about 30, Low (fixture G1).

### 9.3 What is stored

`Incident.risk`, a `RiskAssessment` (contracts 1.1, additive):

| Field | Content |
|---|---|
| `score`, `level` | The integer score and its level (section 11) |
| `factors` | Two rows, each with a plain-language `reason`: `likelihood` (value `L`, contribution `100·L`) and `impact` (value `I`, contribution `100·L·I − 100·L`, zero or negative). The two contributions add up to the unrounded score. The weights are a nominal 1.0: the method multiplies, it does not weight. A dashboard should show the impact row as "points removed by the asset's impact", not as a weighted share |
| `likelihood`, `impact` | `L` and `I` |
| `flags` | `asset_unknown`, `outcome_unknown`, `severity_default`: what the score had to assume |
| `top_contributors` | The 3 strongest groups: technique, entity, strength, strongest event ID and the reason (`S × C × O × D`) |
| `config_version` | `risk.toml`'s `config_version` (`risk-v0`) |
| `computed_at` | `evaluated_at`, passed in by the caller; stored, never used in the maths |

`round_half_up` uses decimal arithmetic (69.5 → 70).

### 9.4 When the score is computed

| Moment | Source |
|---|---|
| When the incident is created | FR-18 |
| Every time the incident is updated (section 7.2) | FR-18, FR-09 |

The score is computed **before and independent of** AI analysis. Re-analysis uses the new score (FR-16). The LLM receives the score and level in the evidence package (`IncidentContext.risk_score`, `risk_level`, OD-03) and explains them. It never changes them (OD-04, FR-19).

**Risk is not confidence.** The AI report confidence and its 0.75 gate belong to AI1 and C5 (OD-16; response workflow spec, section 5). It is a different thing from the event confidence `C_i`. Risk and report confidence are **never combined into one number**.

## 10. Decision record

| Date | Decision | Where |
|---|---|---|
| 29 Oct 2026 | Risk method `q = S·C·O·D`, max per (technique, entity), noisy-OR, `I` max, `Risk = 100·L·I` | Team |
| 29 Oct 2026 | Q1, Q2: impact = NIST FIPS 199, three levels; unknown = 1.0 with `asset_unknown` (four levels may be tried later) | Team |
| 29 Oct 2026 | Q3 source-side entity; Q4 `C` = dataset label trust, `O` success/failed/unknown; Q5 to Q7 dataset clock, 24 h, strong = Backdoors/Backdoor/Worms; Q8 severity from the source value, else the stage; Q9 to Q13 contract 1.1, flagged only, unknown technique 0.5, round then band, host else destination IP | Team (C3 thread, `c3-week2/02-risk-score-gaps-and-questions.md`) |

All values are provisional and are re-tuned in W11 with the thresholds (OD-05). Any change changes `config_version`.

## 11. Thresholds

Thresholds are ratified and provisional until W11 (OD-05). They are configurable (FR-20).

| Level | Score | Source |
|---|---|---|
| Low | < 40 (0 to 39) | OD-05 |
| Medium | 40 to 69 | OD-05 |
| High | ≥ 70 (70 to 100) | OD-05 |

The score is an **estimated severity indicator, not a calibrated probability** (CON-12). A High level is precondition 2 of a freeze (response workflow spec, section 5).

### 11.1 Handoff to C5: risk level and High

This is the C3 to C5 handoff of the Week 2 plan ("risk level field, High threshold definition", due Thu 29 Oct).

| Item | Definition |
|---|---|
| Field | `Incident.risk.level` (`RiskAssessment.level`, contracts v1.0), with the score in `Incident.risk.score`, an integer from 0 to 100 |
| Values | `"low"`, `"medium"`, `"high"` (`RiskLevel` in `backend/app/contracts/common.py`) |
| High | `score >= 70`, boundary inclusive. Medium is 40 to 69, Low 0 to 39 (OD-05) |
| Where the numbers live | `backend/app/correlation/risk.toml`, `[thresholds] medium = 40`, `high = 70`; changing them changes `config_version` |
| Not scored yet | `Incident.risk` is `null` until the score exists (T2-09). Null is **never** High, so it never meets the freeze precondition |
| Freeze (OD-16, owned by C5) | Level High **and** analysis confidence at least 0.75 **and** a valid analysis. C3 provides only the first condition |
| Code | `from app.correlation import is_high, level_for, check_level`. `is_high(incident.risk)` is the freeze precondition (False for null). `level_for(score)` gives the level of a score. `check_level(risk)` raises when a stored level does not match its score, which the contract itself does not check |

C5 should call `is_high` rather than compare numbers, so a W11 threshold change reaches the freeze rule without a code change. Tests: `backend/tests/correlation/test_risk_levels.py`.

## 12. Worked examples

From the shared fixture (`fixtures/correlation/expected-risk.json`, checked by an independent reference in `backend/tests/test_correlation_fixtures.py`). Dataset clock `W` = 20:20, the last fixture event. Fixture asset levels: `db-01` high, `web-01` and `file-01` moderate, `ws-*` low.

### Example 1: attack A, High

| Group (technique, entity) | Strongest event | S | D | q_g |
|---|---|---|---|---|
| Backdoors, 10.10.1.21 | fx-008 | 0.9 (stage 3) | 1 (compromise) | 0.90 |
| Backdoors, svc-db | fx-012 | 0.9 | 1 | 0.90 |
| Exploits, 10.10.1.21 | fx-010 | 0.6 (stage 2) | 0.74 (10.6 h before W) | 0.44 |
| Exploits, 203.0.113.10 and Reconnaissance, 203.0.113.10 | fx-007, fx-004 | 0.6, 0.3 | 0.72 | 0.43, 0.22 |

`L = 1 − (0.1 × 0.1 × 0.56 × 0.57 × 0.78) = 0.9975`. `I` = max(db-01 high 1.0, web-01 0.67, file-01 0.67) = 1.0. Score = round(99.75) = **100, High**. Flag: `outcome_unknown`.

### Example 2: G1, Low because of the asset

Exploits (0.6 × 0.96 = 0.58) then Backdoors (0.9) on `ws-80`: `L = 1 − 0.42 × 0.1 = 0.958`. `I` = ws-80 low 0.33. Score = round(31.6) = **32, Low**. The same evidence on an unrated host would score 96, High.

### Example 3: E, Low

One flagged event without an attack type on `ws-60`: `S` = default 0.5 (flag `severity_default`), `D` = 0.91 (3.3 h before W), `L` = 0.454, `I` = 0.33. Score = **15, Low**.

### All fixture incidents

| Incident | Score | Level | L | I | Flags |
|---|---|---|---|---|---|
| A | 100 | High | 0.998 | 1.00 | outcome_unknown |
| F | 43 | Medium | 0.434 | 1.00 | asset_unknown, outcome_unknown |
| G1 | 32 | Low | 0.958 | 0.33 | outcome_unknown |
| D1 | 21 | Low | 0.642 | 0.33 | outcome_unknown |
| C2 | 19 | Low | 0.575 | 0.33 | outcome_unknown |
| E | 15 | Low | 0.454 | 0.33 | outcome_unknown, severity_default |
| G2a, G2b, G3, G4 | 10 | Low | 0.29 to 0.30 | 0.33 | outcome_unknown |
| D2b, D2a, C1 | 9, 8, 8 | Low | 0.24 to 0.26 | 0.33 | outcome_unknown |

F has no asset at all (no host, IP or user), so it takes the worst-case impact: a single Generic event outranks the DoS incident C2 on a Low workstation. That is the intended effect of "unknown = worst case", and the dashboard shows the `asset_unknown` flag next to it.

## 13. Configuration

The correlation configuration was created in T2-08 and the risk configuration in T2-09. Format and path: TOML files inside the package, `backend/app/correlation/correlation.toml` and `backend/app/correlation/risk.toml`, because the backend image copies only `app/`. Python 3.12 reads TOML with the standard library module `tomllib`, so no dependency is added.

| Key | Default | Used by | Source |
|---|---|---|---|
| `window_minutes` | 15 | Window (section 4) | OD-15 |
| `escalated_window_minutes`, `escalation_min_stage` | 30, 2 | Adaptive memory (section 4) | Team decision 28 Oct 2026 |
| `kill_chain.attack_types` | Section 8 table | Stage per attack type (section 8) | Team decision Q9 |
| `update_idle_windows` | 2 (30 minutes) | Update rule (section 4) | OD-15 |
| `keys` | `["host", "ip_pair", "user"]` | Relatedness keys (section 3) | OD-02 |
| `key_denylist` | `[]` (empty) | Denylist (section 3, proposed) | OD-02 |
| `severity.default`, `severity.stage`, `severity.source_values` | 0.5; stage 1 0.3, 2 0.6, 3 0.9, 4 0.9, 5 0.7; Precinct6 values | `S_i` (section 9.2) | Team, 29 Oct (Q8) |
| `confidence.default`, `confidence.dataset` | 1.0; precinct6 0.8 | `C_i` | Team, 29 Oct (Q4) |
| `outcome.*` | success 1.0, failed 0.5, unknown 1.0; value lists | `O_i` | Team, 29 Oct (Q4) |
| `decay.half_life_hours`, `decay.strong_attack_types` | 24; Backdoors, Backdoor, Worms | `D_i` | Team, 29 Oct (Q5 to Q7) |
| `impact.levels`, `impact.unknown` | low 0.33, moderate 0.67, high 1.0; 1.0 | `I` | Team, 29 Oct (Q1, Q2) |
| `assets` | empty (fixture: `fixtures/correlation/assets.toml`) | `I` | Team, 29 Oct |
| `thresholds.medium` | 40 | Level: Medium from 40 | OD-05, FR-20 |
| `thresholds.high` | 70 | Level: High from 70 | OD-05, FR-20 |
| `config_version` | For example `risk-v0` | Stored in every `RiskAssessment` | AS-04, FR-19 |

Any change to a value in `risk.toml` changes `config_version`, so every stored score can be traced to the configuration that produced it.

## 14. Evaluation

### 14.1 Ground truth

Ground truth comes from the **dataset's documentation**: attack schedules and the attacker and victim hosts. It is built **without the correlation keys** and without any other correlator's output (CON-20, DR-04), so the evaluation does not reward the design for agreeing with itself. The method is written down **by Week 3, before any metric is reported**.

### 14.2 Pairwise metrics over flagged events

A pair of flagged events is **predicted-related** if both are in the same incident, and **truly related** if both are in the same ground-truth incident.

| Count | Meaning |
|---|---|
| TP | Predicted-related and truly related |
| FP | Predicted-related, not truly related |
| FN | Truly related, not predicted-related |

| Metric | Formula |
|---|---|
| Precision P | TP ÷ (TP + FP) |
| Recall R | TP ÷ (TP + FN) |
| F1 | 2PR ÷ (P + R) |

**Worked example.** Five flagged events, two ground-truth incidents.

| | Incidents |
|---|---|
| Ground truth | G1 = {e1, e2, e3}, G2 = {e4, e5} |
| Predicted | I1 = {e1, e2}, I2 = {e3, e4, e5} |

| Pair | Predicted-related | Truly related | Count |
|---|---|---|---|
| e1–e2 | yes | yes | TP |
| e4–e5 | yes | yes | TP |
| e3–e4 | yes | no | FP |
| e3–e5 | yes | no | FP |
| e1–e3 | no | yes | FN |
| e2–e3 | no | yes | FN |
| the other 4 pairs | no | no | (not counted) |

TP = 2, FP = 2, FN = 2. P = 2 ÷ 4 = 0.50, R = 2 ÷ 4 = 0.50, F1 = 2 × 0.5 × 0.5 ÷ (0.5 + 0.5) = **0.50**.

### 14.3 Other metrics

| Metric | Definition | In the example above |
|---|---|---|
| Incorrect merges | Incidents that mix flagged events of two or more ground-truth incidents | 1 (I2 mixes G1 and G2) |
| Missed groups | Ground-truth incidents whose flagged events are split across two or more incidents | 1 (G1 is split over I1 and I2) |
| Alert compression | Flagged events ÷ incidents (one alert per incident, FR-12) | 5 ÷ 2 = 2.5 |
| Runtime | Wall-clock time of a correlation run, with the input size | n/a |

### 14.4 Reproducibility, sensitivity and scope

- **Reproducibility (AS-04).** Two runs on the same input and configuration give identical groups, links, incident types and scores. The algorithm is deterministic (section 5.1, step 2). Any sampling, such as the context events chosen for the evidence package (OD-03), uses a fixed seed.
- **Window sensitivity (W11).** The evaluation is repeated with windows of 5, 10, 15, 30 and 60 minutes.
- **Context attachment** is evaluated separately from flagged-event grouping, so the pairwise metrics above cover flagged events only (C-17).
- **Risk evaluation** is later work (RQ3). It measures agreement between the deterministic score and expert severity ratings, and the sensitivity of the levels to the thresholds and weights. It is planned together with the W11 tuning of OD-05.

## 15. Review and open questions

### Review

| Reviewer | What to check | Status |
|---|---|---|
| C2 | The key fields (`host`, `src_ip`, `dst_ip`, `user`) exist and are filled in the dataset; the event types; the attack-type list from the label mapping (T1-06); whether `privileged_user` is available | pending |
| AI1 | The risk justification explains the deterministic score without changing it (section 9.4); the incident metadata in the evidence package (`incident_type`, `risk_score`, `risk_level`, counts) | pending |
| C5 | The incident type for the scenario lookup (section 8); the update rule against the lifecycle (section 4, section 7.2 and transition T14) | pending |
| Whole team | Risk method and values (section 10, decision record) | agreed 29 Oct 2026 |

### Open questions

Q1 to Q9 were answered by the team on 28 Oct 2026. Q10 to Q16 keep their proposed defaults until the team decides.

| # | Question | Answer or proposed default | Section |
|---|---|---|---|
| Q1 | Is the window boundary inclusive? | Yes: `≤ 15 min` (team, 28 Oct), plus adaptive memory (section 4) | 4 |
| Q2 | Is `ip_pair` unordered? | Yes (team, 28 Oct) | 3 |
| Q3 | Should there be a key denylist? | Yes, empty by default (team, 28 Oct) | 3 |
| Q4 | Is event type a linking key? | No (team, 28 Oct) | 3 |
| Q5 | Can context events merge groups? | No, never (team, 28 Oct) | 6 |
| Q6 | Which group gets a context event that matches several? | Nearest in time; ties to the earliest group (team, 28 Oct) | 6 |
| Q7 | Does an isolated flagged event become an incident? | Yes (team, 28 Oct). Showing only above a threshold is a dashboard and alert filter, not a correlation rule; expiry is the OD-15 idle rule | 7.1 |
| Q8 | Are two open incidents merged when one new event matches both? | No merge; the event joins the older incident (earliest `created_at`, then smallest `incident_id`) and the audit record names the other (team, 28 Oct). A visible `related_incidents` link needs a contract change, planned for Week 3 | 7.2 |
| Q9 | Incident-type rule | Attack type of the most advanced kill-chain stage (team, 28 Oct; section 8) | 8 |
| Q10 | Default severity for an unknown or missing attack type | 0.5, flag `severity_default` (team, 29 Oct) | 9.2 |
| Q11 | Caps for `host_count` and `attack_type_count` | Not used: replaced by the risk method of 29 Oct 2026 (per-group max and noisy-OR) | 9 |
| Q12 | The privileged factor | Not in the risk method of 29 Oct 2026; privilege is not scored in v0 | 9 |
| Q13 | How is an excluded factor stored? | Not applicable: the two factors are always present; assumptions are `flags` | 9.3 |
| Q14 | v0 weights | Replaced by the risk method of 29 Oct 2026 (team); values in section 9.2 | 9, 10 |
| Q15 | Should there be a cap on context events per incident? (The earlier draft proposed 200) | No cap in the incident; the evidence package already caps at 50 events (OD-03) | 6 |
| Q16 | Should there be a maximum incident span? (The earlier draft proposed 2 hours) | None; OD-15 uses only the idle rule | 4 |

## 16. Traceability

| Section | Sources |
|---|---|
| 1. Scope and rules | D2, FR-40, OD-21, OD-04, FR-19, AS-04 |
| 2. Inputs | FR-40, OD-21, CON-20, TD-12, FR-03 |
| 3. Relatedness keys | OD-02, NFR-SF-05 |
| 4. Time window and update rule | OD-15, OD-14, TD-12 |
| 5. Union-find grouping | OD-02, OD-15, AS-04 |
| 6. Context events | OD-02, OD-03, OD-21, FR-40 |
| 7. Incident building | FR-07, FR-08, FR-09, FR-10, FR-11, FR-12, FR-16, FR-18, FR-31, NFR-SF-05, TD-11, OD-15, AS-04 |
| 8. Incident type | OD-20, OD-21 |
| 9. Risk score | OD-04, OD-05, OD-03, OD-16, FR-16, FR-18, FR-19, FR-20, NFR-SF-05, C-17, CON-12 |
| 10. Proposed v0 weights and decision record | OD-04, OD-05 |
| 11. Thresholds | OD-05, FR-20, CON-12 |
| 12. Worked examples | OD-04, OD-05, FR-18 |
| 13. Configuration | OD-02, OD-04, OD-05, OD-15, FR-20, AS-04 |
| 14. Evaluation | AS-04, DR-04, CON-20, C-17, FR-12, OD-03, OD-05 |
| 15. Review and open questions | All of the above |
