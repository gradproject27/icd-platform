# AI1 Week 2: key-fact scoring of the 27 reports (DRAFT, needs review by the whole team)

> **Status: draft, not agreed.** The scores below were drafted with an AI assistant and have **not yet been checked by a person**. They are not the human scoring that `docs/ai1-report-schema.md` section 6 asks for until the team has reviewed them. Every member is asked to check the rows, change any score they disagree with (with a reason), and approve the pull request. Only then can the totals go into section 8 of the report-schema doc.

Rubric (design doc `docs/ai1-report-schema.md`, section 6): for each key fact in `fixtures/ai1/expected.json`
- **2**: stated correctly, with the right events
- **1**: stated vaguely, without the events, or partly wrong
- **0**: missing or wrong

Two reading rules used in this draft (change them if you disagree):
- A fact of the form "X is **not** called malicious / nothing is invented" scores 2 when the report simply does not do it.
- A fact about something that is **absent** ("no sign the requests succeeded", "no system can be named") needs no cited event: there is none to cite.

Reports scored: `docs/ai1-runs/06-week2-qwen3-4b-instruct-10k/reports/` (15) and `docs/ai1-runs/07-week2-llama3.2-3b-8k/reports/` (12; llama's 3 runs of incident E failed G2 and have no report). Events checked against `fixtures/ai1/packages/`.

## Incident A: multi-step attack, risk 100 high (6 facts, max 12 per run)

| Key fact | Qwen r1 | r2 | r3 | llama r1 | r2 | r3 | Reason |
|---|---|---|---|---|---|---|---|
| K1 ip-01 scans and probes host-01 (fx-002, fx-004) | 2 | 2 | 2 | 2 | 2 | 2 | Both cite fx-002 and fx-004. llama says "external address" instead of ip-01 (copied from the event summary): still correct |
| K2 Exploit against host-01 as user-01 (fx-007) | 2 | 2 | 2 | 2 | 2 | 2 | Both correct with fx-007 |
| K3 Reverse shell from host-01 back to ip-01 (fx-008) | **1** | **1** | **1** | 2 | 2 | 2 | Qwen says "back to **ip-02**". In fx-008 ip-02 is host-01's own address and ip-01 is the destination, so the direction is wrong. llama: "back to external address", correct |
| K4 host-01 to host-02 with user-01, then privileged user-02 (fx-009, fx-010) | 2 | 2 | 2 | 2 | 2 | 2 | Both correct. Qwen also names it lateral movement and privilege escalation; llama only repeats the events |
| K5 New services on host-02 and host-03 by user-02 (fx-012, fx-013) | 2 | 2 | 2 | 2 | 2 | 2 | Both correct |
| K6 Context events fx-003, fx-011, fx-014 not called malicious | 2 | 2 | 2 | 2 | 2 | 2 | Neither mentions them |
| **Total** | **11** | **11** | **11** | **12** | **12** | **12** | |

## Incident C1: fuzzing, risk 24 low (3 facts, max 6 per run)

| Key fact | Qwen r1 | r2 | r3 | llama r1 | r2 | r3 | Reason |
|---|---|---|---|---|---|---|---|
| K1 ip-01 sends malformed requests to host-01 twice, 5 min apart (fx-021, fx-022) | 2 | 2 | 2 | **1** | **1** | **1** | Qwen: two steps at 13:00 and 13:05 with each event. llama: one finding citing both events, no "twice", no times |
| K2 The logon of user-01 (fx-023) is context only | **1** | **1** | **1** | **1** | **1** | **1** | Qwen puts the logon in the attack sequence as a "possible follow-up action" (likely_interpretation), though it also says it may be legitimate. llama's text does not mention it, but its answer lists user-01 as an entity of the malformed-requests claim (the U1 warning, confidence 0.0) |
| K3 No sign the requests succeeded | 2 | 2 | 2 | **0** | **0** | **0** | Qwen: "no data compromise or lateral movement is indicated ... not confirmed malicious beyond malformed requests". llama: not stated |
| **Total** | **5** | **5** | **5** | **2** | **2** | **2** | |

## Incident C2: request floods, risk 57 medium (3 facts, max 6 per run)

| Key fact | Qwen r1 | r2 | r3 | llama r1 | r2 | r3 | Reason |
|---|---|---|---|---|---|---|---|
| K1 ip-01 floods host-01 twice, 6 min apart (fx-025, fx-026) | 2 | 2 | 2 | **1** | **1** | **1** | Qwen: two floods at 13:24 and 13:30, each cited. llama: the summary and one finding (fx-026 only), no times, no ip-01 |
| K2 The logon of user-01 to host-02 (fx-024) is context only | **0** | **1** | **1** | **1** | **1** | **1** | Qwen r1: the logon "could have enabled the subsequent DoS attacks", which is wrong. Qwen r2, r3: first step of the attack sequence, but "does not directly support malicious intent". llama: uses the context logon as the reason to check user-01's access |
| K3 Possible loss of availability on host-01 | **1** | **1** | **1** | **0** | **0** | **0** | Qwen calls it a denial-of-service attack on host-01 but never states the availability impact (impact is null). llama: not stated |
| **Total** | **3** | **4** | **4** | **2** | **2** | **2** | |

## Incident E: one flagged event with no attack type, risk 45 medium (2 facts, max 4 per run)

| Key fact | Qwen r1 | r2 | r3 | llama | Reason |
|---|---|---|---|---|---|
| K1 Only one flagged record; the activity is not described | 2 | 2 | 2 | – | Qwen cites fx-032 and says the activity is unknown |
| K2 No attack type is invented | 2 | 2 | 2 | – | Qwen's attack type is null |
| **Total** | **4** | **4** | **4** | not scored | llama: all 3 runs invalid (invented user-01, G2), no report |

## Incident F: one flagged event with no host, IP or user, risk 43 medium (2 facts, max 4 per run)

| Key fact | Qwen r1 | r2 | r3 | llama r1 | r2 | r3 | Reason |
|---|---|---|---|---|---|---|---|
| K1 No affected system can be named | 2 | 2 | 2 | 2 | 2 | 2 | Both say no host, IP or user is present |
| K2 No host, IP or user is invented | 2 | 2 | 2 | 2 | 2 | 2 | Neither names one |
| **Total** | **4** | **4** | **4** | **4** | **4** | **4** | |

## Totals

| Model | Reports scored | Points | Share | Per incident (mean of runs, share of max) |
|---|---|---|---|---|
| Qwen3-4B-Instruct | 15 | 83 of 96 | **0.86** | A 0.92, C1 0.83, C2 0.61, E 1.00, F 1.00 |
| llama3.2 3B | 12 | 60 of 84 | **0.71** | A 1.00, C1 0.33, C2 0.33, E not scored (invalid), F 1.00 |

## What the scoring shows

- **Qwen** gets the facts and the timing right but has two repeated faults: it gets the reverse-shell direction wrong in A (all 3 runs), and it pulls the context logon into the attack story in C1 and C2. The second one is the same fault E6 found, so the planned prompt v1 change (a context event alone supports only a hypothesis) targets it.
- **llama** scores full marks on A only because it copies the event summaries word for word. It names no stages (reconnaissance, lateral movement, privilege escalation). It misses what the small incidents are about: the timing, the lack of success in C1, the availability impact in C2.
- **Limit of the key facts:** they check that facts are stated, not how well the attack is explained. An answer that only repeats the events can score high (llama on A). A sixth fact per incident on the interpretation ("names the stages of the attack") would separate them. Proposed for the next version of `expected.json`, not changed.
- Neither model states the availability impact in C2: the `impact` field was empty in all six reports.

## How to review this sheet

1. Open each report next to its row (paths above) and its package in `fixtures/ai1/packages/`.
2. Comment on the pull request for any score you disagree with, with the reason, or push a change to this file.
3. Check the two reading rules at the top: they decide several scores.
4. When the team agrees, the status line becomes "Reviewed by the team on <date>" and the totals go into `docs/ai1-report-schema.md` section 8.

Not scored here: the reports of runs 8 to 10 (27B model and prompt v1). They can be added after the team agrees on the rubric.
