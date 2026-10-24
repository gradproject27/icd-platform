# Correlation and risk score design

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **Owner** | C3, Detection & Correlation |
| **Task** | T1-08 (Week 1). Implemented in Week 2 by T2-08 (correlation engine v0) and T2-09 (risk score) |
| **Status** | Draft. Items marked **(proposed, needs team agreement)** are C3 design choices, not decisions. Section 15 lists every one of them |
| **Sources** | Ratified decision register (OD-xx, TD-xx, D2); approved requirements (FR-xx, NFR-xx); acceptance scenarios (AS-xx); constraints (CON-xx, C-xx); data requirements (DR-xx); contracts v1 (T1-07, [contracts-v1.md](contracts-v1.md)); [response workflow specification](response-workflow-spec.md) |

## 1. Scope and rules

This document specifies how ICD turns events into incidents and how it computes the deterministic risk score of an incident. C3 implements it in Week 2: the correlation engine v0 in T2-08 and the risk score in T2-09.

It is documentation only. It does not change code, configuration files, migrations, dependencies or the shared contracts. The configuration in section 13 is planned, not created.

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
| `privileged_user` | Privileged factor (section 9) | OD-04 |

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
2. their timestamps differ by 15 minutes or less: `|t₁ − t₂| ≤ 15 min`. The boundary is inclusive (proposed, needs team agreement).

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

## 5. Union-find grouping

Grouping finds the connected components of the "directly related" relation over flagged events (OD-02). It uses a union-find (disjoint-set) structure.

**What is compared.** Only flagged events are compared with each other. Two flagged events are compared only when they share a key value and lie within the window. Unflagged and unlabelled events never take part in grouping (section 6).

### 5.1 Steps

1. **Split** the input events into flagged events (`label.status = flagged`) and context candidates (`unflagged` and `unlabelled`).
2. **Sort** the flagged events by `(timestamp, event_id)`. The tie-break on `event_id` makes the order, and so the result, deterministic.
3. **Make a set** for every flagged event (union-find `make_set`).
4. **Scan** the sorted flagged events. Keep a map `last[key value] → the last flagged event seen with that key value`. For each flagged event `e`, for each of its key values `v`:
   1. if `last[v]` exists and `e.timestamp − last[v].timestamp ≤ window`, **union** `e` with `last[v]`;
   2. set `last[v] = e`.
5. **Collect groups.** Each union-find set is one group of flagged events.
6. **Attach context events** (section 6), then **build incidents** (section 7).

### 5.2 Pseudocode

```text
function group_flagged(events, window, keys, denylist):
    flagged  = [e for e in events if e.label.status == "flagged"]
    context  = [e for e in events if e.label.status in ("unflagged", "unlabelled")]
    flagged  = sort(flagged, by = (e.timestamp, e.event_id))

    uf   = UnionFind()                # path compression + union by rank
    last = {}                         # key value -> last flagged event with that value
    for e in flagged:
        uf.make_set(e)
        for v in key_values(e, keys, denylist):      # e.g. ("host", "ws-17")
            p = last.get(v)
            if p is not None and e.timestamp - p.timestamp <= window:
                uf.union(e, p)        # record v as a link key of e (section 7.1)
            last[v] = e
    return uf.sets(), context

function key_values(e, keys, denylist):
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

Comparing every pair of flagged events would cost `O(n²)`. Comparing only with the last event for each key value gives **the same groups**, because of the sorted order and the gap window:

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
| Context events **never merge groups**. A context event that matches two groups does not union them | Proposed, needs team agreement | OD-02 |
| If a context event matches several groups, it is attached to the group of the flagged event **nearest in time** to it. Ties go to the **earliest group** (earliest `first_event_at`, then smallest first flagged `event_id`) | Proposed, needs team agreement | OD-02 |
| A context event is attached to at most one group | Follows from the rule above | OD-02 |
| A context event is never marked or counted as flagged. It never changes what the dataset label says about the incident ("never treated as malicious", contracts v1 `EventRole`) | Ratified | OD-02, OD-21 |
| Context events alone never create an incident. Every incident has at least one flagged event (contracts v1 validator) | Ratified | OD-02 |
| A context event that matches no group stays in the event store, visible in the event list, outside any incident | Ratified | FR-40 |
| In the evidence package, context events come after all flagged events | Ratified | OD-03 |

**Why context events never merge groups.** A busy server, a shared account or a gateway appears in many unflagged events. If context events could union groups, one such host would chain unrelated incidents into one large incident. Only flagged events, whose labels come from the dataset, decide which groups exist.

**Context events never raise the risk score (proposed, needs team agreement).** The `severity`, `host_count`, `attack_type_count` and `privileged` factors are computed over flagged events only, and `flagged_share` can only go down when context is added (section 9.1).

**Implementation note.** For each key value, keep the flagged events with that value sorted by time. For a context candidate, a binary search per key value finds the nearest flagged event within the window. This keeps attachment at `O(m · k · log n)` for `m` context candidates.

## 7. Incident building

### 7.1 New incidents

| Rule | Status | Source |
|---|---|---|
| Each new group becomes **one incident** in state `New` (transition T01 of the response workflow spec) | Ratified | FR-07, FR-11, TD-11 |
| The incident has one `IncidentEventLink` per event, flagged and context | Ratified | FR-08 |
| Each link stores `role` (`flagged` or `context`) and `link_keys`, the keys that linked the event, so the dashboard can show why events were grouped. The first flagged event in sorted order started the incident and has empty `link_keys`. Any other flagged event lists the keys of the unions it took part in as the later event. A context event lists the keys it shares with the flagged event it was attached to | Ratified (`link_keys`); key rule proposed, needs team agreement | NFR-SF-05 |
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

**v0 rule (proposed, needs team agreement):**

| Step | Rule |
|---|---|
| 1 | Take `label.attack_type` of the incident's **flagged** events. Context events are not counted |
| 2 | The incident type is the **most frequent** attack type |
| 3 | Ties go to the attack type with the **higher severity** in the severity table (section 9; a missing entry counts as the default 0.5) |
| 4 | Remaining ties go to **alphabetical order** |
| 5 | If no flagged event has an attack type, `incident_type = null` ("not classified") |

The type is recomputed whenever the incident is updated. The list of attack types comes from C2's label mapping (T1-06). C5 fills its lookup table (response workflow spec, section 9) from that list.

## 9. Risk score

The risk score is a **weighted factor score computed in code**, with the weights in configuration (OD-04, OD-05). The LLM writes the justification only (FR-19).

### 9.1 Factors

Each factor is normalized to the range 0 to 1. The normalizations are **proposed, needs team agreement**.

| Factor | Definition | Source |
|---|---|---|
| `severity` | Highest severity among the attack types of the incident's flagged events, from the configured table `attack_type → severity` (0 to 1). An attack type missing from the table, or a flagged event without an attack type, uses the default `default_severity = 0.5` | OD-04 |
| `flagged_share` | Flagged events ÷ all events in the incident (flagged plus context) | OD-04 |
| `host_count` | `min(distinct hosts ÷ 5, 1)`, with the cap 5 in configuration. Distinct normalized `host` values among the incident's **flagged** events. Context events are not counted, so attaching context cannot raise this factor | OD-04 |
| `attack_type_count` | `min(distinct attack types ÷ 3, 1)`, with the cap 3 in configuration. Distinct non-null `label.attack_type` values among flagged events | OD-04 |
| `privileged` | Evaluated over the incident's **flagged** events only. 1 if any flagged event has `privileged_user = true`. 0 if at least one flagged event has `privileged_user = false` and none has `true`. **Excluded** when every flagged event has `privileged_user = null`, because the data does not show it ("where the data shows them"). Context events are not counted, so attaching context cannot raise this factor | OD-04 |

**Severity table.** The table is filled after C2's label mapping (T1-06).

> **Example values only.** These rows illustrate the format. They are not proposed values and must not be used.
>
> | `attack_type` | severity |
> |---|---|
> | `reconnaissance` | 0.2 |
> | `brute_force` | 0.6 |
> | `privilege_escalation` | 0.8 |
> | `data_exfiltration` | 0.9 |

### 9.2 Formula

```
score = round_half_up( 100 × Σ(wᵢ × fᵢ) ÷ Σ(wᵢ) )
```

The sums run over the factors that are **not excluded**. The result is an integer from 0 to 100 (FR-18). Dividing by `Σ(wᵢ)` keeps the scale at 0 to 100 when a factor is excluded.

`round_half_up` rounds .5 upward (87.5 → 88). The implementation should use decimal arithmetic, not binary floating point, so that a value such as 87.5 is not turned into 87.4999… before rounding.

### 9.3 What is stored

The score is stored in `Incident.risk` as a `RiskAssessment` (contracts v1):

| Field | Content | Source |
|---|---|---|
| `score` | The integer score | FR-18 |
| `level` | `low`, `medium` or `high` from the thresholds (section 11) | FR-20 |
| `factors` | One `RiskFactor` per **included** factor: `name`, `value` (fᵢ), `weight` (wᵢ), `contribution` = `100 × wᵢ × fᵢ ÷ Σ(wᵢ)` points, unrounded | FR-19, NFR-SF-05, C-17 |
| `config_version` | The `config_version` string of the configuration used | AS-04 |
| `computed_at` | When the score was computed, UTC | FR-18 |

**Excluded factors (proposed, needs team agreement).** An excluded factor is **left out** of `RiskAssessment.factors`. The contract is not changed. The dashboard shows a factor that is configured but missing from `factors` as "not in data". Contributions are unrounded, so they add up to the score before rounding.

With this breakdown, the dashboard shows which factors set the risk (NFR-SF-05, FR-19, C-17).

### 9.4 When the score is computed

| Moment | Source |
|---|---|
| When the incident is created | FR-18 |
| Every time the incident is updated (section 7.2) | FR-18, FR-09 |

The score is computed **before and independent of** AI analysis. Re-analysis uses the new score (FR-16). The LLM receives the score and level in the evidence package (`IncidentContext.risk_score`, `risk_level`, OD-03) and explains them. It never changes them (OD-04, FR-19).

**Risk is not confidence.** The 0.75 confidence gate belongs to AI1 and C5 (OD-16; response workflow spec, section 5). Risk and confidence are **never combined into one number**.

## 10. Proposed v0 weights and decision record

> **Proposed v0 weights (pending team agreement).** This is a proposal for the team meeting, not a decision.
>
> | Factor | Proposed v0 weight | Alternative: earlier C3 draft |
> |---|---|---|
> | `severity` | 0.35 | 0.35 |
> | `flagged_share` | 0.20 | 0.25 |
> | `host_count` | 0.20 | 0.15 |
> | `attack_type_count` | 0.15 | 0.15 |
> | `privileged` | 0.10 | 0.10 |
> | **Sum** | **1.00** | **1.00** |
>
> The proposed v0 weights give equal weight to how many hosts and how much of the incident is flagged. The earlier C3 draft gives more weight to the flagged share. The team can choose either set or set its own.

**Decision record**

| Date | Attendees | Weights agreed | Notes |
|---|---|---|---|
| pending | pending | pending | pending |

**T2-09 does not start until the team has filled in this decision record.** The weights are re-tuned in W11 together with the thresholds (OD-05).

## 11. Thresholds

Thresholds are ratified and provisional until W11 (OD-05). They are configurable (FR-20).

| Level | Score | Source |
|---|---|---|
| Low | < 40 (0 to 39) | OD-05 |
| Medium | 40 to 69 | OD-05 |
| High | ≥ 70 (70 to 100) | OD-05 |

The score is an **estimated severity indicator, not a calibrated probability** (CON-12). A High level is precondition 2 of a freeze (response workflow spec, section 5).

## 12. Worked examples

All three examples use the proposed v0 weights (section 10). Contributions are `100 × wᵢ × fᵢ ÷ Σ(wᵢ)`, shown to two decimals. No input had to be adjusted: every result lands on the expected side of the thresholds.

### Example 1: High

Inputs: severity 0.8, flagged share 0.9, 4 hosts, 3 attack types, privileged true. Σ(wᵢ) = 1.00.

| Factor | Value fᵢ | Weight wᵢ | wᵢ × fᵢ | Contribution (points) |
|---|---|---|---|---|
| `severity` | 0.8 | 0.35 | 0.2800 | 28.00 |
| `flagged_share` | 0.9 | 0.20 | 0.1800 | 18.00 |
| `host_count` | min(4 ÷ 5, 1) = 0.8 | 0.20 | 0.1600 | 16.00 |
| `attack_type_count` | min(3 ÷ 3, 1) = 1.0 | 0.15 | 0.1500 | 15.00 |
| `privileged` | 1 | 0.10 | 0.1000 | 10.00 |
| **Total** | | **1.00** | **0.8700** | **87.00** |

Score = round_half_up(100 × 0.87 ÷ 1.00) = **87 → High** (≥ 70).

### Example 2: Medium

Inputs: severity 0.6, flagged share 0.75, 1 host, 1 attack type, privileged data absent (excluded). Σ(wᵢ) = 0.35 + 0.20 + 0.20 + 0.15 = 0.90.

| Factor | Value fᵢ | Weight wᵢ | wᵢ × fᵢ | Contribution (points) |
|---|---|---|---|---|
| `severity` | 0.6 | 0.35 | 0.2100 | 23.33 |
| `flagged_share` | 0.75 | 0.20 | 0.1500 | 16.67 |
| `host_count` | min(1 ÷ 5, 1) = 0.2 | 0.20 | 0.0400 | 4.44 |
| `attack_type_count` | min(1 ÷ 3, 1) = 0.3333 | 0.15 | 0.0500 | 5.56 |
| `privileged` | excluded, not in `factors` | (0.10) | | |
| **Total** | | **0.90** | **0.4500** | **50.00** |

Score = round_half_up(100 × 0.45 ÷ 0.90) = **50 → Medium** (40 to 69).

### Example 3: Low

Inputs: severity 0.2, flagged share 0.2, 1 host, 1 attack type, privileged false. Σ(wᵢ) = 1.00.

| Factor | Value fᵢ | Weight wᵢ | wᵢ × fᵢ | Contribution (points) |
|---|---|---|---|---|
| `severity` | 0.2 | 0.35 | 0.0700 | 7.00 |
| `flagged_share` | 0.2 | 0.20 | 0.0400 | 4.00 |
| `host_count` | min(1 ÷ 5, 1) = 0.2 | 0.20 | 0.0400 | 4.00 |
| `attack_type_count` | min(1 ÷ 3, 1) = 0.3333 | 0.15 | 0.0500 | 5.00 |
| `privileged` | 0 | 0.10 | 0.0000 | 0.00 |
| **Total** | | **1.00** | **0.2000** | **20.00** |

Score = round_half_up(100 × 0.20 ÷ 1.00) = **20 → Low** (< 40).

### Same examples with the earlier C3 draft weights

| Example | Σ(wᵢ × fᵢ) | Σ(wᵢ) | Score | Level |
|---|---|---|---|---|
| 1 | 0.2800 + 0.2250 + 0.1200 + 0.1500 + 0.1000 = 0.8750 | 1.00 | 87.5 → **88** | High |
| 2 | 0.2100 + 0.1875 + 0.0300 + 0.0500 = 0.4775 | 0.90 | 53.06 → **53** | Medium |
| 3 | 0.0700 + 0.0500 + 0.0300 + 0.0500 + 0.0000 = 0.2000 | 1.00 | 20.0 → **20** | Low |

Example 1 under the earlier draft weights shows the round-half-up rule: 87.5 becomes 88.

## 13. Configuration

The configuration is **planned, not created**. It is created in T2-08 (correlation) and T2-09 (risk). Format and path are **proposed, needs team agreement**: TOML files in `backend/config/`, for example `backend/config/correlation.toml` and `backend/config/risk.toml`. Python 3.12 reads TOML with the standard library module `tomllib`, so no dependency is added.

| Key | Default | Used by | Source |
|---|---|---|---|
| `window_minutes` | 15 | Window (section 4) | OD-15 |
| `update_idle_windows` | 2 (30 minutes) | Update rule (section 4) | OD-15 |
| `keys` | `["host", "ip_pair", "user"]` | Relatedness keys (section 3) | OD-02 |
| `key_denylist` | `[]` (empty) | Denylist (section 3, proposed) | OD-02 |
| `weights.severity`, `weights.flagged_share`, `weights.host_count`, `weights.attack_type_count`, `weights.privileged` | From the decision record (section 10) | Risk score (section 9) | OD-04 |
| `caps.host_count` | 5 | `host_count` factor (proposed) | OD-04 |
| `caps.attack_type_count` | 3 | `attack_type_count` factor (proposed) | OD-04 |
| `default_severity` | 0.5 | `severity` factor and incident-type ties (proposed) | OD-04 |
| `severity_table` | Filled after T1-06 | `severity` factor, incident type | OD-04 |
| `thresholds.medium` | 40 | Level: Medium from 40 | OD-05, FR-20 |
| `thresholds.high` | 70 | Level: High from 70 | OD-05, FR-20 |
| `config_version` | For example `risk-v0` | Stored in every `RiskAssessment` | AS-04, FR-19 |

Any change to the weights, caps, severity table or thresholds changes `config_version`, so every stored score can be traced to the configuration that produced it.

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
| Whole team | v0 weights (section 10, decision record) | pending |

### Open questions

Each question has a proposed default that applies until the team decides.

| # | Question | Proposed default | Section |
|---|---|---|---|
| Q1 | Is the window boundary inclusive? | Yes: `≤ 15 min` | 4 |
| Q2 | Is `ip_pair` unordered? | Yes: A→B and B→A match | 3 |
| Q3 | Should there be a key denylist? | Yes, configurable, empty by default | 3 |
| Q4 | Is event type a linking key? | No, not in v0 | 3 |
| Q5 | Can context events merge groups? | No, never | 6 |
| Q6 | Which group gets a context event that matches several? | The group of the flagged event nearest in time; ties go to the earliest group | 6 |
| Q7 | Does an isolated flagged event become an incident? | Yes, an incident of one event, reported with alert compression | 7.1 |
| Q8 | Are two open incidents merged when one new event matches both? | No; the event joins the incident created first, and the audit record names the other | 7.2 |
| Q9 | Incident-type rule | Most frequent attack type among flagged events; ties by severity, then alphabetical; null if none | 8 |
| Q10 | Default severity for an unknown or missing attack type | 0.5 | 9.1 |
| Q11 | Caps for `host_count` and `attack_type_count`, and which events count hosts | 5 hosts and 3 attack types; both counted over flagged events only | 9.1 |
| Q12 | Which events does the privileged factor use, and what happens when none shows it? | Flagged events only; excluded from the score when every flagged event has `privileged_user = null` | 9.1 |
| Q13 | How is an excluded factor stored? | Left out of `RiskAssessment.factors`; no contract change | 9.3 |
| Q14 | v0 weights | Pending the decision record (section 10) | 10 |
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
