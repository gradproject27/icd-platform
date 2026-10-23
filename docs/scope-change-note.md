# Scope-change note: ICD implementation roadmap vs. approved specification

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **To** | [Supervisor name, title] |
| **From** | [Your name], C1 Platform & Integration, on behalf of the ICD team |
| **Date** | [Date sent] |
| **Task** | T1-02 (Week 1, milestone M1) |
| **Status** | Draft, not yet sent |

## Purpose

The supervisor approved the ICD requirements specification. While planning the implementation, the team made five decisions that differ from it. This note lists each change and its effect on the approved scope, so the specification and the roadmap agree.

None of the changes adds a feature, changes the system's core behaviour, or allows real response actions. All response actions remain simulated, labelled as simulated, and audited.

## Summary of changes

| # | Topic | Approved specification | Roadmap | Effect on approved scope |
|---|---|---|---|---|
| 1 | Prototype date | Prototype (M4) at the end of Week 8 (Section 1.6) | A thinner prototype at the end of Week 4 (Sun 15 Nov 2026). The rest of the original M4 scope moves to the MVP gate (M5, Week 9, Sun 20 Dec 2026). | No scope is removed, only rescheduled. Section 1.6 and the milestone gates in Section 3.6.6 need updating. |
| 2 | Data source | A lab-generated dataset is the primary source (D4). Public datasets are secondary checks, and their role is open (OD-25). | The team's existing dataset is the primary source from Week 1 (ratified 19 Oct 2026). Team-made scenarios fill gaps only in the Phase 4 enhancement. | Requires confirmation that this dataset satisfies D4. If it is not lab-generated, D4, D4.1, OD-25, C-06, A-03, A-08 and Objective 1 need revising. |
| 3 | Correlation ground truth | Lab scenarios provide incident ground truth by construction. | Ground truth comes from the dataset's own documentation, such as attack schedules and attacker and victim hosts. It is built without using the correlation keys. Scripted ground truth exists only for the Phase 4 scenarios. | The evaluation method changes, but the evaluation goal does not. The team will record the method by Week 3. Constraint C-20 still applies. |
| 4 | LLM hosting | Open: a local model or an approved gateway. | An open-weights model on the national HPC. The application runs on a local Docker host. One LLM adapter has three backends: a mock, the HPC, and a small local fallback. | Partly resolves OD-26. NFR-R-08 becomes active. NFR-S-07 (masking host, user and IP fields) applies, because data leaves the application host. |
| 5 | Project duration (TD-9) | 20 weeks, or a 16-week fallback | 20 weeks, from Mon 19 Oct 2026 to Sun 7 Mar 2027. Weeks 12 to 14 run at reduced capacity because of exams. | Closes TD-9. The 16-week fallback is no longer needed. |

## Requested from the supervisor

1. Acknowledge the five changes above.
2. For change 2, confirm whether the team's dataset satisfies D4 as written. If it does not, approve revising the dependent items listed above.

The team will update the specification sections named above after the supervisor's reply.
