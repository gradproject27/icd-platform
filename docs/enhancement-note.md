# Enhancement note: features added beyond the approved specification

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **To** | [Supervisor name, title] |
| **From** | [Your name], on behalf of the ICD team |
| **Date** | [Date sent] |
| **Basis** | Competitor feature study ([research/competitor-feature-study.md](research/competitor-feature-study.md)); decision D4 |
| **Status** | Draft, not yet sent |

## Purpose

The team studied how open-source and commercial SOC products (Wazuh, Elastic Security, Security Onion, Splunk ES, Microsoft Sentinel and Security Copilot, IBM QRadar) implement features ICD lacked. From that study it added seven small features. The [scope-change note](scope-change-note.md) says the roadmap adds no feature, so this note asks you to acknowledge them as **enhancements**.

None of them changes the approved core behaviour:
- ICD still has no detection layer (D2);
- the risk score is still computed only by code (OD-04);
- the freeze gate and the 60-second analyst window are unchanged (OD-16, OD-17);
- every response action stays simulated, labelled and audited;
- the AI model receives nothing new.

## The enhancements

| # | Enhancement | What the analyst gains | Inspired by | Pull request |
|---|---|---|---|---|
| P1 | Incident key facts | Where and when the incident started, its source, assets, ports and accounts, computed by code with cited events, beside the AI report | Microsoft Security Copilot's incident summary | #52 (merged) |
| P2 | Timed simulated containment | A simulated IP block ends on its own after 60 min, longer for a repeat source (120, 240), and is audited | Wazuh stateful active response | #53 |
| P3 | Entity risk roll-up | Which sources are riskiest across incidents, and which used many ATT&CK tactics. Read-only, beside the incident score | Elastic entity risk score; Splunk risk-based alerting | #57 |
| P4 | ATT&CK tactic table | The MITRE ATT&CK tactics of each incident, from a reviewed table (never from the AI) | Splunk, Elastic and Wazuh ATT&CK mapping | #56 |
| P5 | Count and order markers | "Reconnaissance, then exploitation, on web-01" style markers over flagged events; they flag nothing | Wazuh frequency rules; Elastic EQL sequences | #58 |
| P6 | Scenario impact and recent decisions | Each simulated scenario's impact and how it is reverted; the decisions of the last 72 hours | Elastic AlertZero | #59 |
| P7 | ECS export | An upload's events as Elastic Common Schema for other tools | Elastic Common Schema | #60 |

Also: the repository is now under the **MIT License** (#55). Datasets keep their own terms (licence register), and no dataset row is in the repository.

## How the work stayed inside the rules

- **Sources:** only public documentation and open-source repositories were read. No commercial product was installed, decompiled or used.
- **Clean-room:** no competitor code was copied. The only third-party material, MITRE ATT&CK tactic names and ECS field names, is used under its licence with the required notice (`THIRD_PARTY_NOTICES.md`).
- **Tests:** each enhancement has its own tests. The backend suite grew from 1,042 to 1,150 tests and the frontend from 220 to 246; all pass in CI.

## Requested from the supervisor

1. Acknowledge P1 to P7 as enhancements to the approved scope.
2. Say whether any of them should be removed or held back before the MVP gate (M5).
