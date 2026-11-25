# Competitor feature study

| | |
|---|---|
| Project | ICD (Intelligent Cyber Defense) |
| Scope | How open-source and commercial SOC products implement ten features ICD lacks or does differently (F-A to F-J) |
| Status | Sections 1 to 14: the read-only study (Phase 1, 25 Nov 2026, PR #51). Section 15: the outcome, meaning the decisions, what was built and what was rejected (Phase 4, 25 Nov 2026) |
| Built | P1 to P7 and the MIT licence: #52 (merged), then #53 and #55 to #60 in merge order, and the final record PR. See section 15 |

## 1. Method and rules

- **Labels.** Every claim carries one label. **Verified**: read in the cited file or page. **Inferred**: my conclusion from code or text I read, with the reasoning given. **Cannot verify**: not found in an authorized source.
- **Authorized sources only.** Open-source repositories were cloned shallowly (one commit, needed folders only) outside the ICD repo, into `../competitors/`. Splunk ES/SOAR, IBM QRadar, Microsoft Sentinel and Security Copilot were studied from their **public documentation only**. No product binaries, trials or consoles were used.
- **Licence first.** Each section states the licence of the code read and a reuse mode:
  - **clean-room**: re-implement from this description only;
  - **copy with notice**: only MIT, Apache-2.0 or BSD sources, recorded in `THIRD_PARTY_NOTICES.md`;
  - **reference only**: ideas or public facts, no code or text reused.
  ICD has no `LICENSE` file yet, so no GPL, AGPL or ELv2 code may be copied (Verified: `ls LICENSE*` in the repo root finds nothing).
- **REA** ([morluto/rea](https://github.com/morluto/rea), MIT, version 6.10.1) was used only where it adds something: auditing ICD's own frontend build (section 13). The competitors in scope publish their source, so their source was read directly.
- **ICD's design rules apply.** Rule 1 (no detection layer, D2) and Rule 2 (the risk score is code, OD-04) in [correlation-and-risk-design.md](../correlation-and-risk-design.md#1-scope-and-rules) are hard constraints for every proposal in Phase 2.

### Sources and commits read

| Source | Commit or version | Licence (Verified from the licence file or page) |
|---|---|---|
| wazuh/wazuh tag `v4.14.10` | [`6e7835b`](https://github.com/wazuh/wazuh/tree/6e7835b4880c3210ef30e855a6bb43432be792e1) | GPL-2.0, with an OpenSSL exception (`LICENSE`) |
| wazuh/wazuh `main` (5.1.0-alpha0) | [`6cc7b2e`](https://github.com/wazuh/wazuh/tree/6cc7b2ec51eb2be1d2252a3cec6908648a14f245) | `src/engine/` AGPL-3.0-or-later; `src/shared_modules/*` GPL-2.0 OR AGPL-3.0-or-later; the rest GPL-2.0 (`LICENSE`, lines 1 to 26) |
| wazuh/wazuh-documentation `main` (documents 5.1.0, pre-release) | [`7380690`](https://github.com/wazuh/wazuh-documentation/tree/7380690fa13da17832fed3caae96d9780d82c837) | GPL-2.0-or-later (`README.md:41`; no LICENSE file) |
| elastic/kibana `main` | [`19217f6`](https://github.com/elastic/kibana/tree/19217f6ffc33be5b64980a3662bb74fdc295b0d7) | `x-pack/` Elastic License 2.0 only; elsewhere triple AGPL-3.0 / SSPL-1 / ELv2 unless the header says otherwise (`LICENSE.txt`) |
| elastic/detection-rules `main` | [`06a05eb`](https://github.com/elastic/detection-rules/tree/06a05eb45d6e10d8f4ddc24ac88edcd5c4f47ee6) | Elastic License 2.0 (`LICENSE.txt`) |
| elastic/ecs `main` (9.6.0-dev) | [`153ecde`](https://github.com/elastic/ecs/tree/153ecde1932d6df36fad68ca18befc6c1756c1f6) | Apache-2.0 (`LICENSE.txt`) |
| elastic/docs-content `main` | [`96870a9`](https://github.com/elastic/docs-content/tree/96870a908ce76d263fa01d5f4c4e687be43e1c99) | **CC BY-NC-ND 4.0** (`LICENSE`): no derivatives |
| Security-Onion-Solutions/securityonion | [`eb17d45`](https://github.com/Security-Onion-Solutions/securityonion/tree/eb17d45a4cd54233eaa8eebd528df47cea1efea2) | Elastic License 2.0 (`LICENSE`) |
| Security-Onion-Solutions/securityonion-docs | [`499531f`](https://github.com/Security-Onion-Solutions/securityonion-docs/tree/499531f0ee4ccdceb615b611b791b844e5d0c1cb) | Cannot verify: `license.rst` describes the product's licences, not the docs' own |
| splunk/security_content | [`689e177`](https://github.com/splunk/security_content/tree/689e177da0c31da9154b51d3dbdd2af40462a03c) | Apache-2.0 (`LICENSE`) |
| Azure/Azure-Sentinel | [`8c576c3`](https://github.com/Azure/Azure-Sentinel/tree/8c576c31ec30b313aac446d57b1e7f0e644994cb) | MIT (`LICENSE`) |
| SigmaHQ/sigma | [`7228ccc`](https://github.com/SigmaHQ/sigma/tree/7228cccddc63a771924ab585e072f4fbb63690fb) | Rules: **Detection Rule License 1.1** (`LICENSE`) |
| splunk/botsv1, botsv2, botsv3 | `97fb3f2`, `47cd23b`, `5f556f8` | CC0 1.0 (`LICENSE`). The repos hold only a README and licence; the data is downloaded separately and was not downloaded |
| Splunk ES 8.8, Microsoft Learn | Public documentation, read 25 Nov 2026 | Reference only (vendor documentation) |

Corrections to the licence facts we started from (all Verified from the files above):

1. **AlertZero's action workflows are not ELv2-only.** They live under Kibana's `src/` tree (for example `src/platform/packages/shared/kbn-workflows/managed/definitions/alertzero/actions/action_close_alerts_false_positive.ts`). Their header licenses them under ELv2, AGPL-3.0 only, or SSPL-1, at the user's election. The Security Solution plugin and Attack Discovery code under `x-pack/` are ELv2-only, as expected.
2. **elastic/docs-content is CC BY-NC-ND 4.0.** Facts may be cited, but no text may be adapted.
3. **SigmaHQ rules use the Detection Rule License 1.1,** not a permissive code licence.
4. **Wazuh `main` no longer has the classic rule engine.** `src/analysisd` and the XML rules are absent at `6cc7b2e`, and `VERSION.json` says 5.1.0 alpha0. F-A and F-B were therefore read at tag `v4.14.10`, whose `VERSION.json` says stage `rc2`.

## 2. Summary

| ID | Feature | Competitor | ICD component | ICD today | Licence of what was read | Reuse mode |
|---|---|---|---|---|---|---|
| F-A | Rule chaining and frequency/timeframe/same-field correlation | Wazuh 4.14 | C3 | Gap-window union-find over shared keys; no rule chaining, no count threshold | GPL-2.0 | clean-room |
| F-B | Stateful response that reverts after a timeout; longer timeouts for repeat offenders | Wazuh 4.14 | C5 | Isolation is released only by an analyst (S4) or a reject | GPL-2.0 | clean-room |
| F-C | Entity risk score: rank-weighted sum, 0–100, asset-criticality odds update, five bands | Elastic | C3 | Per-incident noisy-OR × FIPS 199 impact, three bands | ELv2 | clean-room |
| F-D | EQL sequences, building-block alerts, a "shell" alert over the sequence | Elastic | C3 | Order-free grouping; kill-chain stage only widens the window | ELv2 | clean-room (idea only) |
| F-E | Proposed actions: approve/decline, 72 h expiry, per-action impact/reversible/approval policy, autonomy levels | Elastic AlertZero | C5, C4 | 60 s window, three options, system selection at expiry | ELv2/AGPL/SSPL code; CC BY-NC-ND docs | clean-room |
| F-F | Attack Discovery fields and "drop discoveries citing unknown alert IDs" validation | Elastic | AI1 | Per-claim grounding G0 to G5, U1 | ELv2 | reference only |
| F-G | Import node for pcap/evtx; Sigma rules via ElastAlert | Security Onion | C1, C2 | CSV upload of UNSW-NB15 only | ELv2 (code); docs licence unknown | reference only |
| F-H | Risk-based alerting: risk per entity, 24 h > 100, ≥ 3 tactics in 7 days, risk factors | Splunk ES 8 (docs), security_content | C3, C2 | No cross-incident entity risk; no ATT&CK tactics | Docs: reference; content: Apache-2.0 | reference only; copy with notice possible |
| F-I | Copilot incident summary fields; Fusion and Defender XDR entity correlation; approval playbooks | Microsoft (docs), Azure-Sentinel | AI1, C3, C5 | AnalysisReport 1.0; entity keys host/ip_pair/user | Docs: reference; playbooks: MIT | reference only; copy with notice possible |
| F-J | ECS field names for the normalized schema | Elastic ECS | C2 | ICD's own Event field names | Apache-2.0 | copy with notice (field names only) |

## 3. F-A: Wazuh rule correlation (C3)

**How it works (Wazuh 4.14.10, `src/analysisd`)**

- **Verified.** A rule can depend on an earlier rule having fired. The XML options `if_matched_sid` ([rules.c:176](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/analysisd/rules.c#L176)), `same_field` ([rules.c:189](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/analysisd/rules.c#L189)) and many `different_*` and `not_same_*` options ([rules.c:202-227](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/analysisd/rules.c#L202-L227)) are parsed into the rule. A rule with `if_matched_sid` searches the recent events of that SID with `Search_LastSids` ([rules.c:1968](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/analysisd/rules.c#L1968)).
- **Verified.** `frequency` must be 2 to 9999, and the parser stores `frequency - 2` ([rules.c:2317-2325](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/analysisd/rules.c#L2317-L2325)). The default `timeframe` is 360 s ([rules.c:242](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/analysisd/rules.c#L242)).
- **Verified.** `Search_LastSids` ([eventinfo.c:99-272](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/analysisd/eventinfo.c#L99-L272)) walks the earlier matches from newest to oldest. It stops at the first one older than `timeframe`, measured against the **current wall-clock time** (`w_get_current_time()`, lines 136 and 143). Unless the rule is global, it requires the same agent (lines 148-156). It then requires equal values for each `same_*` field (lines 158-200). The rule fires when enough matches remain (lines 247-257), and it keeps up to about ten earlier log lines with the alert (`add_lastevt`, lines 243-245).
- **Inferred.** Given the `- 2` and the `<` comparison, the rule fires on the event that brings the in-window count to `frequency`, counting the current event. I did not run Wazuh to confirm the exact off-by-one.
- **Verified example.** Rule 5712 fires at level 10 on 8 matches of rule 5710 ("non-existent user") from the same source IP within 120 s, maps to ATT&CK T1110, and carries compliance groups ([0095-sshd_rules.xml:109-118](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/ruleset/rules/0095-sshd_rules.xml#L109-L118)).
- **Verified.** Rule levels run from 0 to 16 in the current documentation ([rules-classification.rst:10](https://github.com/wazuh/wazuh-documentation/blob/7380690fa13da17832fed3caae96d9780d82c837/source/user-manual/ruleset/rules/rules-classification.rst?plain=1#L10)). This page documents 5.1.0, so the 4.x range may differ (Cannot verify for 4.x).

**ICD today**

- **Verified.** Flagged events are grouped with union-find. A flagged event links to the previous flagged event with the same key value when the gap is within 15 min, or 30 min once the chain reaches kill-chain stage 2 ([engine.py:102-117](../../backend/app/correlation/engine.py#L102-L117); [correlation.toml:7-16](../../backend/app/correlation/correlation.toml#L7-L16)).
- **Verified.** Time is the **dataset clock**, the event timestamps, not the time of analysis ([correlation-and-risk-design.md, section 2](../correlation-and-risk-design.md#2-inputs)).

**Gap**

- **Inferred.** ICD has no rule that says "N flagged events of attack type X on the same key within T, then mark the incident" and no "event B after event A on the same key" chaining. Every incident is a connected component, with no count or order condition.
- **Inferred.** Wazuh compares against wall-clock time, which suits live streams. ICD analyses uploaded historical files, so any re-implementation must use event timestamps.
- **Inferred.** Wazuh rules *detect* (they raise new alerts from raw logs). Under Rule 1, a version for ICD may only work over events the dataset already flagged. It could add a marker or factor to an incident, but it must never flag an event.

**Licence and reuse.** GPL-2.0. **Clean-room.** Only the concepts (count threshold, time window, same-field condition, dependent rule) may be reused.

## 4. F-B: Wazuh stateful Active Response with automatic revert (C5)

**How it works (Wazuh 4.14.10, `src/os_execd`, `src/active-response`)**

- **Verified.** Scripts receive JSON with a `command` of `add` or `delete` ([active_responses.c:86-89](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/active-response/active_responses.c#L86-L89)). Before acting, a script can answer `check_keys`, and `execd` replies `continue` or `abort` ([execd.c:324-336](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/os_execd/execd.c#L324-L336) and [execd.c:449-452](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/os_execd/execd.c#L449-L452)).
- **Verified.** With a non-zero timeout, `execd` stores a timeout entry that holds the same JSON with `command` rewritten to `delete`, a key (`rkey`, the script name plus the alert keys the script chose) and the time of addition ([execd.c:345-430](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/os_execd/execd.c#L345-L430), with the rewrite at line 414).
- **Verified.** If the same key arrives again while the entry exists, Wazuh does not stack it: it only resets the time of addition ("Command already received, updating time of addition to now", [execd.c:388-401](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/os_execd/execd.c#L388-L401)).
- **Verified.** `ExecdTimeoutRun` runs the stored `delete` once `now - time_of_addition > time_to_block`, then drops the entry ([execd.c:139-197](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/os_execd/execd.c#L139-L197)).
- **Verified.** For repeat offenders, a per-key counter selects a longer timeout from `repeated_offenders_timeout`, configured in minutes ([execd.c:346-373](https://github.com/wazuh/wazuh/blob/6e7835b4880c3210ef30e855a6bb43432be792e1/src/os_execd/execd.c#L346-L373)). The 5.1 docs describe up to six increasing values, for example `1,5,10` ([active-response.rst:38-74](https://github.com/wazuh/wazuh-documentation/blob/7380690fa13da17832fed3caae96d9780d82c837/source/user-manual/reference/ossec-conf/active-response.rst?plain=1#L38-L74)).
- **Verified (5.1 docs).** "A stateful active response executes an action for a specified period and automatically reverts it when the configured timeout expires" ([types-of-active-response.rst:11-14](https://github.com/wazuh/wazuh-documentation/blob/7380690fa13da17832fed3caae96d9780d82c837/source/user-manual/capabilities/active-response/types-of-active-response.rst?plain=1#L11-L14)). The 5.1 docs call the revert command `disable`, while the 4.14 code uses `delete` (Verified in both places).
- **Verified (absence).** Within the Wazuh files read, Active Response has no human approval step. It runs when the rule matches.

**ICD today**

- **Verified.** A freeze applies simulated isolation, and a 60 s window opens ([response.toml:6-8](../../backend/app/response/response.toml#L6-L8)). Isolation ends only when an analyst picks S4 ([response.toml:39-42](../../backend/app/response/response.toml#L39-L42); [executor.py:40-42](../../backend/app/response/executor.py#L40-L42)) or rejects during a freeze ([lifecycle.py:30](../../backend/app/response/lifecycle.py#L30)).
- **Verified.** The S1 to S3 scenarios (keep isolation, block IP, disable account) have no duration ([response.toml:24-37](../../backend/app/response/response.toml#L24-L37)).

**Gap**

- **Inferred.** ICD's simulated actions are open-ended. A block or isolation never records a planned end, never ends on its own, and does not escalate for an entity that returns.
- **Inferred.** A version for ICD would add a planned duration and an expiry job that writes a "reverted (simulated)" action and an audit record, the same way `expire_due` handles windows ([engine.py:680-699](../../backend/app/response/engine.py#L680-L699)). Nothing real would change; everything stays labelled SIMULATED ([executor.py:21](../../backend/app/response/executor.py#L21)).

**Licence and reuse.** GPL-2.0. **Clean-room.**

## 5. F-C: Elastic entity risk scoring (C3)

**How it works (Kibana `main`, `x-pack/solutions/security/plugins/security_solution`)**

- **Verified.** Per entity (host, user or service), an ES|QL query takes the entity's alerts and computes `MV_PSERIES_WEIGHTED_SUM(TOP(risk_score, sampleSize, "desc"), 1.5)` ([calculate_esql_risk_scores.ts:186-192](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/risk_score/calculate_esql_risk_scores.ts#L186-L192)). This is Σ rᵢ / i^1.5 over the alerts sorted by score. The exponent is `RIEMANN_ZETA_S_VALUE = 1.5` and the default sample is 500 alerts ([constants.ts:15,24](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/risk_score/constants.ts#L15-L24)).
- **Verified.** The sum is divided by the partial zeta sum for that sample size, giving `normalized_score` ([parse_esql_row.ts:88](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/risk_score/maintainer/steps/parse_esql_row.ts#L88); [constants.ts:26-70](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/risk_score/constants.ts#L26-L70)). The maximum is 100 ([constants.ts:75](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/risk_score/constants.ts#L75)). The ten top inputs are kept as the explanation ([constants.ts:80](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/risk_score/constants.ts#L80)).
- **Verified.** Asset criticality multipliers: extreme 2, high 1.5, medium 1, low 0.5 ([asset_criticality/constants.ts:55-60](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/common/entity_analytics/asset_criticality/constants.ts#L55-L60)). They are applied as a **Bayesian odds update**, not a plain multiplication: with odds = s / (100 − s), the new score is 100·m·odds / (1 + m·odds) ([helpers.ts:64-81](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/asset_criticality/helpers.ts#L64-L81)). Watchlist modifiers multiply into the same modifier ([apply_score_modifiers.ts:115-135](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/entity_analytics/risk_score/apply_score_modifiers.ts#L115-L135)).
- **Verified.** Levels: Unknown 0–20, Low 20–40, Moderate 40–70, High 70–90, Critical 90–100 ([risk_levels.ts:11-17](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/common/entity_analytics/risk_engine/risk_levels.ts#L11-L17)).

**ICD today**

- **Verified.**
  - q_i = S·C·O·D per flagged event.
  - Keep the strongest per (technique, entity).
  - L = 1 − ∏(1 − q_g) (noisy-OR).
  - score = round(100 · L · I), where I is the highest FIPS 199 impact of the incident's assets (low 0.33, moderate 0.67, high 1.0, unknown 1.0).
  - Levels: Low < 40, Medium 40–69, High ≥ 70.

  Sources: [risk.toml:3-13,62-70](../../backend/app/correlation/risk.toml#L3-L13); [risk.py:219-262](../../backend/app/correlation/risk.py#L219-L262).
- **Verified.** The score is per **incident**. The entity used for grouping is source IP, else user, else host ([risk.py:139-147](../../backend/app/correlation/risk.py#L139-L147)). Nothing adds up risk for an entity across incidents.

**Worked comparison (Inferred, calculated with the formulas above; ICD groups assumed distinct)**

| Inputs (scores 0–100) | Elastic normalized (sample 500, zeta 2.523) | ICD noisy-OR × I = 1 |
|---|---|---|
| one at 73 | 28.9 | 73 |
| three at 73 | 44.7 | 98 |
| two at 50 | 26.8 | 75 |
| ten at 100 | 79.1 | 100 |

Asset modifier on a score of 50, Elastic odds update: ×0.5 → 33.3, ×1 → 50, ×1.5 → 60, ×2 → 66.7. ICD's impact multiplier on 50: low → 16.5, moderate → 33.5, high → 50.

**Gap**

- **Inferred.** The two designs answer different questions. Elastic asks "how risky is this entity over everything it did", is deliberately conservative, and never reaches 100 through criticality. ICD asks "how strong is this incident", saturates quickly, and only lowers the score through impact.
- **Inferred.** ICD lacks a separate, deterministic **entity risk view** across incidents, and a criticality modifier that can raise as well as lower. Either would be additions beside the incident score, not replacements, because the freeze gate depends on the incident score (OD-16).

**Licence and reuse.** ELv2 (`x-pack`). **Clean-room.** The formula is a standard p-series with a Bayesian odds update; ICD would write its own code and its own TOML values.

## 6. F-D: Elastic EQL sequences and building-block alerts (C3)

- **Verified.** EQL rules can require an ordered sequence on one key within a time span, for example `sequence by process.entity_id with maxspan=5m` ([command_and_control_aws_iot_secure_tunneling_localproxy.toml:96-99](https://github.com/elastic/detection-rules/blob/06a05eb45d6e10d8f4ddc24ac88edcd5c4f47ee6/rules/cross-platform/command_and_control_aws_iot_secure_tunneling_localproxy.toml#L96-L99)).
- **Verified.** For a matched sequence of N events, Kibana writes N building-block alerts plus one "shell" alert that ties them together ([build_alert_group_from_sequence.ts:63-66](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/solutions/security/plugins/security_solution/server/lib/detection_engine/rule_types/eql/build_alert_group_from_sequence.ts#L63-L66)).
- **Verified.** A rule marked `building_block_type = "default"` ([collection_archive_data_zip_imageload.toml:9](https://github.com/elastic/detection-rules/blob/06a05eb45d6e10d8f4ddc24ac88edcd5c4f47ee6/rules_building_block/collection_archive_data_zip_imageload.toml#L9)) produces alerts that are "hidden from the Alerts page by default", serving as intermediate signals ([choose-the-right-rule-type.md:36](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/detect-and-alert/choose-the-right-rule-type.md?plain=1#L36)). `rules_building_block/` holds 131 rule files, and `grep -rl building_block_type` finds the marker in all 131 (Verified).

**ICD today.** **Verified.** Grouping ignores order. The kill-chain stage only widens the window to 30 min ([engine.py:6-10](../../backend/app/correlation/engine.py#L6-L10)) and picks the incident type ([engine.py:92-99](../../backend/app/correlation/engine.py#L92-L99)).

**Gap.** **Inferred.** ICD cannot express "stage 1 then stage 3 on the same key within T" as a named pattern, and the dashboard does not separate the events that complete such a pattern from context events. Two parts could fit Rule 1 if they apply only to flagged events:
- an ordered-pattern **marker** on an incident (not a new detection);
- a "building block" style role for events shown only on request.

**Licence and reuse.** ELv2 (rules and Kibana `x-pack`); docs CC BY-NC-ND. **Clean-room** for the idea. No rule text or query is reused.

## 7. F-E: Elastic AlertZero proposed actions (C5, C4)

All of the following is **Verified** in Elastic's docs (CC BY-NC-ND, cited, not adapted) and in Kibana's workflow definitions.

- A Worker "brings it to you as a proposed action" with an investigation that "holds the Worker's evidence and conclusion, so you can check its reasoning before you approve or decline" ([alertzero/index.md:16](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/alertzero/index.md?plain=1#L16)).
- "Every Worker starts at Manual autonomy … changes to detection rules always wait for you" ([index.md:33](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/alertzero/index.md?plain=1#L33)). Higher levels let some Workers approve their own actions, and Supervised lets endpoint analysis isolate hosts without waiting ([configure-worker-settings.md:169-175](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/alertzero/configure-worker-settings.md?plain=1#L169-L175)).
- "Each proposed action expires 72 hours after a Worker proposes it. If nobody decides before then, the action doesn't run, and the proposed action shows Expired" ([work-in-alertzero.md:22](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/alertzero/work-in-alertzero.md?plain=1#L22)).
- Status values: Needs review, Applying, Applied, Declined, Failed, Expired ([glossary.md:89](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/alertzero/glossary.md?plain=1#L89)). Closed decisions of the last 72 h are listed, naming the Worker when a Worker decided on its own ([work-in-alertzero.md:36](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/alertzero/work-in-alertzero.md?plain=1#L36)).
- A "Minimum confidence score" setting: false positives below it stay open as inconclusive ([configure-worker-settings.md:59-60](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/alertzero/configure-worker-settings.md?plain=1#L59-L60)). **Cannot verify** the default value: it is not stated on the page.
- Each action workflow declares metadata such as `impact`, `reversible` and `approvalPolicy`. For example, host isolation has `impact: high`, `reversible: true` and `approvalPolicy: autonomy-dependent` (`.../alertzero/actions/defend/action_isolate_host.yaml`, lines 20-23, at commit `19217f6`). Kibana's tests also check an `always-gate` policy (`git grep` result, workflow tests under the same folder).

**ICD today**

- **Verified.** One proposal path: a freeze, a fixed 60 s window, three analyst options, and system selection at the deadline ([response.toml:6-8,44-47](../../backend/app/response/response.toml#L6-L8); [response-workflow-spec.md, section 8](../response-workflow-spec.md#8-the-three-analyst-options)).
- **Verified.** Scenarios carry `automatic = true|false` (S4 is analyst-only, [response.toml:39-42](../../backend/app/response/response.toml#L39-L42)). The confidence threshold of 0.75 gates the freeze ([freeze.py:57](../../backend/app/response/freeze.py#L57)).

**Gap**

- **Inferred.** ICD's design is the opposite end of the same spectrum. It acts first (simulated isolation) with a very short window and selects at the deadline, where AlertZero waits up to 72 h and never runs an undecided action.
- **Inferred.** Ideas that fit ICD without changing OD-17 (the fixed 60 s window):
  - per-scenario metadata (impact, reversible, approval policy), in the spirit of `automatic`;
  - an explicit **Expired / not run** outcome for non-freeze recommendations in the review queue;
  - "closed decisions of the last N hours" with who or what decided.
- Changing the 60 s window itself is out of scope unless the team reopens OD-17.

**Licence and reuse.** Workflow code: ELv2 / AGPL-3.0 / SSPL-1. Docs: CC BY-NC-ND. **Clean-room** design only.

## 8. F-F: Elastic Attack Discovery output vs ICD AnalysisReport (AI1)

- **Verified.** An attack discovery requires `alertIds`, `detailsMarkdown`, `summaryMarkdown` and `title`, and also has `entitySummaryMarkdown`, `mitreAttackTactics` and `timestamp` ([common_attributes.schema.yaml:9-44](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/platform/packages/shared/kbn-elastic-assistant-common/impl/schemas/attack_discovery/common_attributes.schema.yaml#L9-L44)). The stored alert form adds `replacements` (anonymization), `riskScore`, workflow status, assignees and the connector used ([attack_discovery_alert.schema.yaml:23-111](https://github.com/elastic/kibana/blob/19217f6ffc33be5b64980a3662bb74fdc295b0d7/x-pack/platform/packages/shared/kbn-elastic-assistant-common/impl/schemas/attack_discovery/attack_discovery_alert.schema.yaml#L23-L111)).
- **Verified.** The default validation "removes discoveries that reference alert IDs that were not part of the analysis (hallucinated IDs)", then deduplicates ([configure-alert-retrieval-from-attacks-page.md:84-86](https://github.com/elastic/docs-content/blob/96870a908ce76d263fa01d5f4c4e687be43e1c99/solutions/security/ai/attack-discovery/configure-alert-retrieval-from-attacks-page.md?plain=1#L84-L86)).

**ICD today**

- **Verified.** AnalysisReport 1.0 has summary, attack type, ordered sequence steps with cited event IDs, findings categorised evidence-supported / likely / hypothesis, weaknesses, impact, recommendations, risk justification, uncertainty, confidence and grounding counts ([report.py:21-124](../../backend/app/contracts/report.py#L21-L124)).
- **Verified.** The grounding check makes an answer invalid when:
  - (G1) it cites an event outside the package;
  - (G3) it names an unknown IP or masked token, or **any** ATT&CK technique ID;
  - (G5) it states a different risk score.

  Unsupported entity claims only lower the grounding rate (U1) ([grounding.py:1-15](../../backend/app/analysis/grounding.py#L1-L15)).

**Gap**

- **Inferred.** ICD's check is stricter and finer than Attack Discovery's documented default. ICD judges per claim, rejects the whole answer and records counts; Attack Discovery drops whole discoveries. Two things ICD lacks:
  - an `entitySummary`-style one-line headline;
  - ATT&CK tactics.
- **Inferred.** ATT&CK tactics cannot come from the model under the current rules: G3 rejects technique IDs because the package carries no technique knowledge. Tactics would have to come from deterministic data, such as a reviewed `attack_type → tactic` table, before the report could show or cite them.

**Licence and reuse.** ELv2. **Reference only**: field ideas, no schema text copied.

## 9. F-G: Security Onion Import node and Sigma via ElastAlert (C1, C2)

- **Verified.** `so-import-pcap` imports pcaps and keeps their original timestamps. It runs Suricata (IDS alerts) and Zeek (network metadata), stores both in Elasticsearch, and gives a link to view them ([so-import-pcap.rst:6-12](https://github.com/Security-Onion-Solutions/securityonion-docs/blob/499531f0ee4ccdceb615b611b791b844e5d0c1cb/so-import-pcap.rst?plain=1#L6-L12)). An Import Node is the minimal install for this, and uploads can also go through the Grid UI ([so-import-pcap.rst:14-21](https://github.com/Security-Onion-Solutions/securityonion-docs/blob/499531f0ee4ccdceb615b611b791b844e5d0c1cb/so-import-pcap.rst?plain=1#L14-L21)). `so-import-evtx` does the same for Windows event logs ([so-import-evtx.rst:6-10](https://github.com/Security-Onion-Solutions/securityonion-docs/blob/499531f0ee4ccdceb615b611b791b844e5d0c1cb/so-import-evtx.rst?plain=1#L6-L10)). The scripts are `salt/common/tools/sbin_jinja/so-import-pcap` and `so-import-evtx` (Verified in `git ls-files`).
- **Verified.** "Sigma rules are loaded into ElastAlert to monitor incoming logs … Active sigma rules generate alerts" ([sigma.rst:6](https://github.com/Security-Onion-Solutions/securityonion-docs/blob/499531f0ee4ccdceb615b611b791b844e5d0c1cb/sigma.rst?plain=1#L6); [detections.rst:9](https://github.com/Security-Onion-Solutions/securityonion-docs/blob/499531f0ee4ccdceb615b611b791b844e5d0c1cb/detections.rst?plain=1#L9)).

**ICD today**

- **Verified.** Upload of a file to a registered parser. Only `fixture` and `unsw-nb15` have parsers ([README, Frontend](../../README.md#frontend)). Precinct6 and OTRF are planned for Week 5 ([README, status](../../README.md#project-status)).
- **Verified.** OTRF techniques are kept as dataset metadata, never as a per-event label ([label-mapping.json:182](../../backend/app/ingest/mappings/label-mapping.json#L182)). The repository has no `.pcap` files (Verified with `git ls-files`).

**Gap**

- **Inferred.** The *import* pattern fits ICD: replay a historical file and keep its original timestamps, which ICD already does with CSV. The Suricata, Zeek and Sigma part is a **detection layer**, so it conflicts with Rule 1 (D2). An evtx parser for the OTRF dataset (Week 5 plan) would be C2's normal parser work, not detection.
- **Inferred.** pcap import would need tshark or Zeek. Neither is installed (Phase 0), and UNSW-NB15 is used as CSV.

**Licence and reuse.** ELv2 (code); Sigma rules DRL 1.1. **Reference only.** Importing Sigma rules into ICD would also break Rule 1.

## 10. F-H: Splunk risk-based alerting (C3) and security_content (C2)

From Splunk ES 8.8 public docs (**Verified** quotes, read 25 Nov 2026; reference only):

- "In Splunk Enterprise Security version 8.0 and higher, the term intermediate finding replaces risk events and the term finding replaces notable events" ([findings](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.8/findings/monitor-your-security-operations-center-with-findings-in-splunk-enterprise-security)). Intermediate findings "are not displayed in the analyst queue" ([use detections](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.8/detections/use-detections-to-search-for-threats-in-splunk-enterprise-security)).
- "Findings Risk Threshold Exceeded for Entity Over 24 Hour Period … creates findings when the risk score for an object exceeds 100 over the last 24 hours" ([finding-based detections](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.8/detections/finding-based-detections-available-in-splunk-enterprise-security)).
- "Findings ATT&CK Tactic Threshold Exceeded for Entity Over Previous 7 Days … Creates findings when the number of MITRE tactics exceeds 3 over the last 7 days" (same page). **The page contradicts itself:** the search shown uses `mitre_tactic_id_count >= 3 and contributing_source_count >= 4`. So "≥ 3 tactics" is what the code says, and a fourth condition (4 sources) is not in the prose.
- Risk factors: `(risk_base_score + sum(addition factors)) * product(multiplication factors)`, additions first. ES ships seven default factors, all turned off, for example Admin user ×1.5, Critical priority destination ×1.5, High priority user ×1.25, Contractor user +5 ([risk factors](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.8/risk-based-alerting/adjusting-risk-using-risk-factors-in-splunk-enterprise-security)).
- An investigation holds at most 100 findings, and each finding has one parent investigation ([findings and finding groups](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.8/investigations/findings-and-finding-groups-in-splunk-enterprise-security)).

From splunk/security_content (Apache-2.0, **Verified**):

- A detection declares `finding: {title, entity: {field, type, score}}`, `threat_objects`, `mitre_attack_id` and drill-downs over 7 days of risk events. Example: LSASS access, entity `dest` of type `system`, score 50, technique T1003.001 ([access_lsass_memory_for_dump_creation.yml:38-61](https://github.com/splunk/security_content/blob/689e177da0c31da9154b51d3dbdd2af40462a03c/detections/endpoint/access_lsass_memory_for_dump_creation.yml#L38-L61)).
- A `type: Correlation` detection sums `calculated_risk_score` and counts distinct tactics and techniques per risk object from the Risk data model ([okta_risk_threshold_exceeded.yml:8-17](https://github.com/splunk/security_content/blob/689e177da0c31da9154b51d3dbdd2af40462a03c/detections/application/okta_risk_threshold_exceeded.yml#L8-L17)).

**ICD today.** **Verified.** No per-entity risk across incidents (see F-C), no ATT&CK tactic data on events or incidents ([grounding.py:7-8](../../backend/app/analysis/grounding.py#L7-L8)), and no additive or multiplicative risk factors beyond S, C, O, D and I.

**Gap**

- **Inferred.** Splunk's model is two-level. Many small scored observations per entity are summed, and only a threshold crossing (score or tactic diversity) reaches the analyst. ICD's flagged events already play the "observation" role, so an *entity risk roll-up with thresholds* is the closest addition. It needs a deterministic tactic source first (F-F).
- **Inferred.** Splunk detections are detection content. ICD could only use their `attack_type → technique/tactic` style metadata, never the searches (Rule 1).

**Licence and reuse.** Docs: **reference only**. security_content: Apache-2.0, so **copy with notice** is allowed (for example a technique-to-tactic table), but no copy is proposed yet.

## 11. F-I: Microsoft Security Copilot, Sentinel and Defender XDR (AI1, C3); Azure-Sentinel playbooks (C5)

Public Microsoft Learn pages (**Verified** quotes, read 25 Nov 2026; reference only):

- **Copilot incident summary.** "An incident summary, depending on the availability of the data, includes":
  - attack start time;
  - the entity or asset where it started;
  - a timeline summary;
  - the assets involved;
  - IoCs;
  - threat actor names;
  - suggested prompts.

  "Incidents containing up to 100 alerts can be summarized into one incident summary." Summaries are cached for a week ([incident summary](https://learn.microsoft.com/en-us/defender-xdr/security-copilot-m365d-incident-summary), ms.date 2026-06-15). MITRE techniques are not in that list.
- **Copilot accuracy.** "Security Copilot can produce responses that are inaccurate, incomplete, or outdated. … Users should apply human judgment and validate critical outputs." Also: "Security Copilot includes AI disclosure and cites source materials … but users should still make sure to verify the accuracy of responses" ([application card](https://learn.microsoft.com/en-us/copilot/security/security-copilot-application-card), ms.date 2026-06-22).
- **Fusion.** Fusion is "a correlation engine based on scalable machine learning algorithms". For workspaces onboarded to the Defender portal, "Fusion is disabled. Its functionality is replaced by the Microsoft Defender XDR correlation engine". "After March 31, 2027, Microsoft Sentinel will no longer be supported in the Azure portal" ([Fusion](https://learn.microsoft.com/en-us/azure/sentinel/fusion)). **Cannot verify** Fusion's internal model: Microsoft does not publish it.
- **Sentinel alert grouping.** Three modes: all entities match, all alerts of the rule, or selected entities and details match. Grouping is limited to a selected time frame. "Up to 150 alerts can be grouped into a single incident." Re-opening closed incidents is not available after Defender onboarding ([create analytics rules](https://learn.microsoft.com/en-us/azure/sentinel/create-analytics-rules), ms.date 2026-11-12). **Cannot verify** a 7-day maximum: the page does not state it.
- **Defender XDR correlation.** It merges on "Entities", "Artifacts", "Time frames" and "Sequences of events that point to multistage attacks", and "Incidents that are resolved don't get reopened" ([alerts and incidents correlation](https://learn.microsoft.com/en-us/defender-xdr/alerts-incidents-correlation), ms.date 2026-11-15). The priority score is "from 0 to 100", using inputs such as severity, MITRE techniques, asset criticality and alert rarity ([incident queue](https://learn.microsoft.com/en-us/defender-xdr/incident-queue), legacy page). **Cannot verify** the weights: they are not published.

Azure/Azure-Sentinel playbooks (MIT, **Verified**):

- `Block-AADUserOrAdmin/incident-trigger` disables the account first, then asks for approval. "If you select Approve - admin will stay disabled … If you select Reject - admin account will be re-enabled" ([azuredeploy.json:318-332](https://github.com/Azure/Azure-Sentinel/blob/8c576c31ec30b313aac446d57b1e7f0e644994cb/Playbooks/Block-AADUserOrAdmin/incident-trigger/azuredeploy.json#L318-L332)).
- `AS-Incident-Response-Approval-Email` sends an Approve/Reject email to the user's manager before closing the incident as benign ([azuredeploy.json:252-255](https://github.com/Azure/Azure-Sentinel/blob/8c576c31ec30b313aac446d57b1e7f0e644994cb/Playbooks/AS-Incident-Response-Approval-Email/azuredeploy.json#L252-L255)).

**ICD today**

- **Verified.** Entity keys host, ip_pair and user, a gap window, and a 500-event size cap ([correlation.toml:7-22](../../backend/app/correlation/correlation.toml#L7-L22)).
- **Verified.** Report fields as in F-F.
- **Verified.** Freeze first, then decide, where a reject releases the isolation ([lifecycle.py:30](../../backend/app/response/lifecycle.py#L30)).

**Gap**

- **Inferred.** ICD's "act, then let a person confirm or undo" design matches the shape of Microsoft's own sample playbook. That is evidence for the design rather than a gap.
- **Inferred.** Missing report fields compared with the Copilot summary: an explicit **start time and starting entity**, and an **IoC list**. ICD can derive these deterministically from the incident's events (first flagged event; distinct IPs/ports) instead of asking the model, which keeps G-checks simple.
- **Inferred.** Sentinel's "all entities match" versus "selected entities" grouping is a configurable choice ICD does not offer. ICD links on *any* shared key value.

**Licence and reuse.** Docs: **reference only**. Playbooks: MIT, so **copy with notice** is allowed, but they are Azure Logic Apps JSON with nothing to copy into ICD. Reference only in practice.

## 12. F-J: ECS field names for ICD's Event (C2)

**Verified** ECS rows from [generated/csv/fields.csv](https://github.com/elastic/ecs/blob/153ecde1932d6df36fad68ca18befc6c1756c1f6/generated/csv/fields.csv) (ECS 9.6.0-dev on `main`; a released tag should be pinned before use):

| ICD Event field ([event.py](../../backend/app/contracts/event.py)) | ECS field | ECS row |
|---|---|---|
| `timestamp` | `@timestamp` | 2 |
| `ingested_at` | `event.ingested` | 537 |
| `event_id` | `event.id` | 536 |
| `event_type` | `event.category` / `event.type` (arrays, fixed vocabularies) | 529, 551 |
| `host` | `host.name` | 898 |
| `src_ip`, `dst_ip` | `source.ip`, `destination.ip` | 1911, 285 |
| `src_port`, `dst_port` | `source.port`, `destination.port` | 1916, 290 |
| `protocol` | `network.transport` (tcp/udp) or `network.protocol` (application) | 1068, 1067 |
| `user` | `user.name` | 2690 |
| `summary` | `message` | 4 |
| `provenance.dataset_id` | `event.dataset` | 532 |
| original record | `event.original` | 540 |
| `label.status`, `label.attack_type` | no direct field; `event.kind` (`alert` vs `event`) is the nearest | 538 |
| (none in ICD) | `threat.tactic.id`, `threat.technique.id` | 2371, 2374 |

**Inferred.**
- The mapping is almost one-to-one, so an **ECS export view** (Event → ECS JSON) is cheap and would let ICD data load into Elastic or Wazuh tooling.
- Renaming the Event contract itself would break six contracts, the frontend types and the tests, so it is not recommended.
- ICD's `label` has no ECS equivalent and must stay an ICD extension.

**Licence and reuse.** Apache-2.0. **Copy with notice** for field names, if a mapping file is generated from ECS.

## 13. REA audit of ICD's own frontend build

Done because the brief names it ("auditing ICD's own frontend build"), and because ICD's dashboard is the one shipped artifact the project owns.

- Build: `npm ci` then `npm run build` in `frontend/`. The output is three files: `index.html`, a 9.5 kB CSS file and a 347.7 kB JS file. `dist/` and `node_modules/` are git-ignored, and `git status` stayed clean (Verified).
- `rea audit-release-exposure frontend/dist --json` (REA 6.10.1) reported:
  - `no_exposure_observed_in_assessed_checks: true`;
  - 0 exposed, 2 not observed (extractable payload, native debug companions), 3 not applicable, 3 not assessed, 7 **unknown**.

  The unknowns are honest: REA's text scan reads at most 262,144 bytes per file, and the 347.7 kB bundle exceeds it. So the credential-marker and source-map checks did not cover the main bundle (Verified from the report's `coverage.omitted`).
- Covering that gap by hand (Verified, `grep` on the bundle):
  - 0 `sourceMappingURL` comments;
  - no keys or tokens; the only "password" strings are React DOM's input handling;
  - the only URLs are `http://localhost`, W3C namespaces and React or router documentation links.
- Conclusion (Inferred): the production dashboard ships no source maps and no secrets. Re-run the check whenever `vite.config` or the build changes.

## 14. What could not be verified

| Item | Why |
|---|---|
| "400,000 GitHub stars" for REA | Not in the installed README (6.10.1); the only popularity badge is an image |
| Exact frequency off-by-one in Wazuh | Read from code only; Wazuh was not run |
| Wazuh 4.x rule level range | The docs read describe 5.1.0 (0 to 16) |
| AlertZero default minimum confidence score | Not stated on the documentation page |
| Fusion's ML model and Defender's priority weights | Not published by Microsoft |
| Sentinel grouping maximum time frame | Not stated on the page read |
| Splunk ES internals (how factors are stored, data model fields) | Commercial software; public docs only, and they partly disagree (see F-H) |
| IBM QRadar | Not part of features F-A to F-J; public docs not studied in this phase |
| Licence of securityonion-docs text | `license.rst` describes the product, not the docs |

## 15. Outcome

### 15.1 Decisions

Phase 2 (25 Nov 2026): the project lead chose P1 and P2. Afterwards they asked for **every remaining item to be finished, deciding by the study's recommendations**. The outcome:

| ID | Decision | Outcome |
|---|---|---|
| D1 | Which features | **All of P1 to P7**, one PR each |
| D2 | ICD's licence | **MIT** for code and docs; datasets excluded (#55). Needs every author's consent before merge |
| D3 | Shared contract changes | **None.** Every feature adds API shapes only. P5 moved from the planned `Incident.patterns` contract field into the key facts to keep this |
| D4 | Scope against the specification | **Note written:** [../enhancement-note.md](../enhancement-note.md), for the team to send to the supervisor |
| D5 | P2 durations | 60 min, then 120 and 240 min for repeats of S2's IP block; S1 and S3 never end on their own |
| D6 | P3 formula and thresholds | Rank-weighted sum (exponent 1.5) over the top **10** incident scores, normalised to 0–100; 24 h dataset-clock window; flags at score ≥ 70 and ≥ 3 tactics; no asset criticality for source entities. C3 to confirm |
| D7 | P4 mapping | Rows map only what the category name implies, anchored to a technique of that tactic in MITRE's STIX data; Generic and Analysis unmapped. Marked Inferred; C3 writes, AI1 reviews |
| D8 | Branch naming | `claude/<slug>`, as requested |
| D9 | LLM hosting | No feature depends on it; nothing new is sent to a model |

### 15.2 What was added

| | Feature | From (read only) | PR | Tests added (backend / frontend) |
|---|---|---|---|---|
| P1 | Incident key facts (`GET /incidents/{id}/key-facts`), computed by code from flagged events with cited events | Microsoft Copilot incident summary (docs) | #52, merged | 17 / 8 |
| P2 | Timed simulated containment: S2's IP block ends on its own, repeat offenders longer, one audit record per revert (migration 0007) | Wazuh stateful active response (GPL-2.0) | #53 | 28 / 6 |
| — | MIT licence, `THIRD_PARTY_NOTICES.md` | — | #55 | — |
| P4 | ATT&CK tactic table (`tactics.toml`) in key facts. Tactic names come from MITRE's STIX data, which renames TA0005 to "Stealth" and adds TA0112 | Splunk, Elastic, Wazuh ATT&CK mapping | #56 | 13 / 1 |
| P3 | Entity risk roll-up (`GET /entity-risk`, Entities page), read-only | Elastic entity risk (ELv2); Splunk RBA (docs) | #57 | 18 / 4 |
| P5 | Count and order markers in key facts (`patterns.toml`), over flagged events only | Wazuh frequency rules; Elastic EQL sequences | #58 | 14 / 2 |
| P6 | Scenario impact metadata (`GET /scenarios`) and decisions of the last 72 h (`GET /decisions/recent`) | Elastic AlertZero (ELv2/AGPL/SSPL; CC BY-NC-ND docs) | #59 | 11 / 5 |
| P7 | ECS 9.5.0 NDJSON export (`GET /uploads/{id}/ecs`); field names checked in the release | ECS (Apache-2.0) | #60 | 7 / — |

Every feature is clean-room. The only third-party material, MITRE ATT&CK tactic IDs and names and the ECS field names, is used under its licence with the notice in `THIRD_PARTY_NOTICES.md`. Test totals with all PRs: **1150 backend** (990 passed and 160 skipped without a database) and **246 frontend**, against 1042 and 220 before the study. CI passes on every PR.

**Nothing in the list changes** the risk score (OD-04), the freeze gate (OD-16), the 60 s window (OD-17), the six contracts, the evidence package, the prompts or the grounding checks. No event is flagged by ICD (D2).

### 15.3 What was rejected, and why

| Idea | Source | Why rejected |
|---|---|---|
| Sigma rules via ElastAlert, Suricata or Zeek alerts | Security Onion (F-G) | A detection layer: breaks D2. Sigma rules are also DRL 1.1 |
| pcap import | Security Onion (F-G) | ICD's datasets are CSV; no tshark or Zeek; no `.pcap` in the repo |
| Replacing ICD's risk formula with Elastic's | Elastic (F-C) | Overturns OD-04 and the team's method; P3 sits beside the incident score instead |
| Renaming the Event contract to ECS names | ECS (F-J) | Breaks six contracts, the frontend and the tests; P7's export view gives the interoperability |
| A BOTS v1–v3 parser | Splunk BOTS | C2-D21 (no extra parsers before the Week 5 plan); the data needs a Splunk install to read |
| Copying any competitor code | All | Everything was re-implemented; GPL, AGPL, SSPL and ELv2 code is never copied |
| AlertZero-style 72 h approvals | Elastic AlertZero (F-E) | Would reopen OD-17; only the metadata and the 72 h history were taken (P6) |
| Asset criticality in the entity roll-up | Elastic (F-C) | ICD's entities are mostly sources (attackers); incident scores already carry asset impact |

### 15.4 Deferred proposals

None. P3 to P7 were built in the second round (15.2).

### 15.5 Open items (for the team; none can be done by a pull request)

1. **Merge in order:** #53, #54, #55, #56, #57, #58, #59, #60, then the final record PR. Each needs an approving review (CONTRIBUTING). The stack is built so that each merges without conflicts; GitHub re-targets each PR to `main` when the one below it is merged and its branch deleted.
2. **#55, licence:** every team member agrees to MIT before merging.
3. **Supervisor:** fill in and send [../enhancement-note.md](../enhancement-note.md).
4. **Reviews of two judgement calls:** the P4 tactic table (C3 and AI1; D7) and the P3 numbers (C3; D6). Changing a value means a new `config_version`.
5. **Clean-up after merging:** delete the `claude/pr-assets` branch, which only holds the screenshots shown in #52 and #53.
6. **Not verified** (section 14) stays as recorded: REA's stars badge, Wazuh's exact frequency count, AlertZero's default confidence, Fusion and Defender internals, and the UNSW-NB15 category definitions (the dataset page lists only names; the paper's page refused automated reads).

### 15.6 Every PR of this work

| PR | Branch | Content | Base |
|---|---|---|---|
| [#51](https://github.com/gradproject27/icd-platform/pull/51) | `claude/competitor-feature-study` | This study, sections 1 to 14 | merged (`8c95c24`) |
| [#52](https://github.com/gradproject27/icd-platform/pull/52) | `claude/incident-key-facts` | P1 | merged (`8992488`) |
| [#53](https://github.com/gradproject27/icd-platform/pull/53) | `claude/timed-containment` | P2 (with `main` merged in, `db658e0`; no force-push) | `main` |
| [#54](https://github.com/gradproject27/icd-platform/pull/54) | `claude/competitor-study-wrap-up` | First version of this section | `main` |
| [#55](https://github.com/gradproject27/icd-platform/pull/55) | `claude/licence` | MIT licence, notices | #53 |
| [#56](https://github.com/gradproject27/icd-platform/pull/56) | `claude/attack-tactics` | P4 | #55 |
| [#57](https://github.com/gradproject27/icd-platform/pull/57) | `claude/entity-risk` | P3 | #56 |
| [#58](https://github.com/gradproject27/icd-platform/pull/58) | `claude/incident-patterns` | P5 | #57 |
| [#59](https://github.com/gradproject27/icd-platform/pull/59) | `claude/scenario-metadata` | P6 | #58 |
| [#60](https://github.com/gradproject27/icd-platform/pull/60) | `claude/ecs-export` | P7 | #59 |
| Final record PR | `claude/final-wrap-up` | This section, README status, supervisor note (includes #54) | #60 |
