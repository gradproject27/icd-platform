# Dataset profile

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **Owner** | C2, Security Data & Ingestion |
| **Task** | T1-05 (Week 1) |
| **Status** | v1, for team review. Items marked **(proposed)** are C2 choices, not decisions. Section 10 lists every open question |
| **Profiled** | 24 Oct 2026, against the Event contract v1 ([contracts-v1.md](contracts-v1.md), section 3.1; owner C3) |
| **Sources** | Data plan (9 rows); decision register (D4, OD-21, OD-25); requirements (FR-02 to FR-05, FR-40, FR-41, NFR-S-07); constraints (CON-20, DR-04); [correlation-and-risk-design.md](correlation-and-risk-design.md); licence register [dataset-licence-register.md](dataset-licence-register.md) |

## 1. Purpose and scope

This document records what is in each data source of the team's data plan, measured, not estimated. It says which Event fields each source can fill, what its labels mean, what is wrong with the data, and what ground truth exists for evaluating correlation.

It is documentation only. No dataset record is in the repo. The data, the profiling scripts and their full output live outside the repo:

| What | Where (not committed) |
|---|---|
| Downloaded data | the team's local data folder, one subfolder per source |
| Scripts | `c2-profiling/` next to the repo: `fetch_sources.py`, `profile_dataset.py`, `selfcheck.py` |
| Full profile | `c2-profiling/out/profile.json` and `c2-profiling/out/profile-summary.md` |
| Manifest with SHA-256 per file | `c2-profiling/out/sources-*.json` |

To regenerate: `python -I fetch_sources.py <data folder>`, then `python -I profile_dataset.py <data folder>`, then `python selfcheck.py <data folder> --rehash`. Every number below comes from `profile.json` of 24 Oct 2026.

The 9 rows of the data plan and how deep each was profiled this week:

| Row | Source | Role in the data plan | Profiling this week |
|---|---|---|---|
| 1 | Generated scenarios (scenario generator) | Primary correlation benchmark; truth by construction; simulated detector for Option B | register only (not built yet) |
| 2 | Precinct6 | ML pair training; realism and agreement check. Small sample first, larger slice later | full (small variant, slice) |
| 3 | OTRF Security Datasets | Technique truth, ATT&CK mapping, AI report tests. Replaces building most of the lab | full (APT29 day 1 and 2, two atomic sets) |
| 4 | NVD, KEV, EPSS, ATT&CK, CIRCL, NIST | Knowledge base for AI reports. Snapshot and hash | snapshot |
| 5 | CIC-IDS2017 or UNSW-NB15, one only | CSV demo and ingestion test. Not used for detection training | full, **not profiled yet** (files not downloaded; follow-up PR) |
| 6 | Own lab with Atomic Red Team and Caldera | Only for techniques OTRF does not cover | register only (no data yet) |
| 7 | Splunk BOTS | Optional second independent source if Months 3 and 4 have spare time | register only |
| 8 | TON_IoT | Dropped from the critical path. Its sources do not join into incidents and detection is out of scope | register only |
| 9 | LANL, CERT, Loghub | Stretch or parser tests | LANL, CERT: register only; Loghub: full (2k samples) |

Row 1 is the primary source of the data plan (D4). The public datasets in rows 2 to 9 are secondary; their role is still open (OD-25).

## 2. Provenance and versions

All downloads were made on 24 Oct 2026 (UTC) and pinned to a revision where the source has one. The manifest holds the URL, revision, download time, size and SHA-256 of all 133 downloaded files. The six Precinct6 data files also match the SHA-256 values that Hugging Face publishes for that revision.

| Source | URL or repo ID | Pinned revision | Files | Total size (bytes) | Largest file |
|---|---|---|---|---|---|
| Precinct6 | `witfoo/precinct6-cybersecurity` (Hugging Face, small variant) | `96311c2e`, card v2.1.0 | 16 | 4,670,121,413 | `graph/incidents.jsonl` (4,490,700,959) |
| OTRF | `OTRF/Security-Datasets` (GitHub) | `d9d40ef1` | 14 | 59,851,665 | `apt29_evals_day2_manual.zip` (43,033,041) |
| APT29 emulation plan | `mitre-attack/attack-arsenal` (GitHub) | `201db70f` | 6 | 46,737 | `Emulation_Plan/Day 1/README.md` (15,456) |
| Loghub | `logpai/loghub` (GitHub) | `dd61d095` | 51 | 10,872,803 | `OpenStack_2k.log_structured.csv` (719,703) |
| MITRE ATT&CK | `mitre-attack/attack-stix-data` (GitHub) | `c2494b29` | 2 | 55,272,368 | `enterprise-attack.json` (55,271,014) |
| CISA KEV | https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json | catalogue 2026.10.23 | 1 | 1,807,090 | the catalogue JSON |
| FIRST EPSS | https://epss.empiricalsecurity.com/epss_scores-current.csv.gz | model v2026.06.15, scores of 2026-10-24 | 1 | 2,769,604 | the scores CSV (gzip) |
| NVD | CVE API 2.0, `resultsPerPage=1` | API 2.0 | 1 | 2,517 | one API response |
| CIRCL | `CIRCL/vulnerability-attack-techniques` (data); cards of `vulnerability-scores`, `vulnerability-cwe-patch` | `319c3e32`; `34e6a141`; `5f6c8f60` | 11 | 2,245,585 | `train-00000-of-00001.parquet` (2,037,241) |

The remaining files are licence pages, cards and API metadata (listed in the manifest). UNSW-NB15 and CIC-IDS2017 need a browser download (SharePoint folder; CIC download form) and are not in the data folder yet.

Precinct6 slice: the repo holds 51,390 files (about 7.84 GB). Not downloaded, because the same content is in another format: `graph/edges.jsonl`, `graph/graph.graphml`, `graph/nodes.jsonl`, `graph/attack_reports.jsonl` and the 51,371 files under `graph/incidents_graphml/`. The 100M variant is not used.

## 3. Inventory per source

### 3.1 Precinct6 (per subset)

| Subset | File | Format | Size (bytes) | Records |
|---|---|---|---|---|
| signals (live capture) | `signals/signals.parquet` | Parquet, 38 columns | 117,056,748 | 2,011,674 |
| incident_signals (historical leads) | `signals/incident_signals.parquet` | Parquet, 38 columns | 10,518,589 | 238,511 |
| graph nodes | `graph/nodes.parquet` | Parquet, 19 columns (flattened) | 4,325,154 | 47,585 |
| graph edges | `graph/edges-00000.parquet` | Parquet, 41 columns (flattened) | 35,821,982 | 1,740,438 |
| attack reports | `graph/attack_reports.parquet` | Parquet, 6 columns | 4,177,754 | 51,371 |
| incidents | `graph/incidents.jsonl` | JSON lines | 4,490,700,959 | 51,371 (with 480,536 embedded leads and 229,769 embedded nodes) |

The node and edge counts match `graph/metadata.json` exactly (47,585 and 1,740,438). No `artifact_id` appears in both signal tables.

### 3.2 OTRF

| Dataset | File | Format | Size (bytes) | Records |
|---|---|---|---|---|
| APT29 day 1 | `apt29_evals_day1_manual.zip` | zip, one JSON-lines member (385,334,029 unzipped) | 13,944,973 | 196,081 |
| APT29 day 2 | `apt29_evals_day2_manual.zip` | zip, one JSON-lines member (1,714,987,031 unzipped) | 43,033,041 | 587,286 |
| APT29 day 1 Zeek | `day1/zeek/combined_zeek.log` | JSON lines, 14 log streams | 1,243,861 | 2,140 |
| APT29 day 2 Zeek | `day2/zeek/combined_zeek.log` | JSON lines, 18 log streams | 1,542,562 | 5,664 |
| Atomic SDWIN-201018195009 (credential access) | `psh_lsass_memory_dump_comsvcs.zip` | zip, JSON lines | 17,957 | 184 |
| Atomic SDWIN-200806015757 (lateral movement) | `covenant_copy_smb_CreateRequest.zip` | zip, JSON lines | 25,786 | 506 |
| APT29 emulation plan | `emulationplans/apt29.xlsx` and the attack-arsenal Day 1 and Day 2 READMEs | xlsx, markdown | 25,051 (xlsx) | 10 + 10 steps |

The Windows events are grouped by `Channel`. APT29 day 1 has 11 channels; the largest is `Microsoft-Windows-Sysmon/Operational` (143,884 events). Day 2 has 11 channels; Sysmon has 407,265 events.

### 3.3 Loghub

16 systems, each with a 2,000-line raw sample (`*_2k.log`) and its parsed CSV (`*_2k.log_structured.csv`, header row): 32,000 structured rows in total. The full logs are on Zenodo (record 8196385, 19 files, about 5.58 GB) and were not downloaded.

### 3.4 UNSW-NB15 and CIC-IDS2017

Not profiled yet. The official pages document: UNSW-NB15, "The total number of records is two million and 540,044 which are stored in the four CSV files" (research.unsw.edu.au UNSW-NB15 page, retrieved 24 Oct 2026); CIC-IDS2017, a labelled-flow archive `GeneratedLabelledFlows.zip` (www.unb.ca CIC-IDS2017 page, retrieved 24 Oct 2026). A follow-up PR adds the measured inventory.

### 3.5 Snapshot sources

| Source | Version | Records |
|---|---|---|
| CISA KEV | catalogue 2026.10.23 | 1,756 |
| FIRST EPSS | model v2026.06.15, score date 2026-10-24 | 395,249 |
| MITRE ATT&CK enterprise | ATT&CK 20.0, STIX 2.1 | 26,690 objects: 227 techniques, 479 sub-techniques, 15 tactics (active); 161 revoked or deprecated |
| NVD | CVE API 2.0 | `totalResults` 413,906 (not bulk-downloaded) |
| CIRCL vulnerability-attack-techniques | `319c3e32` | 1,207 (1,086 train, 121 test) |
| NIST | SP 800-61r3 (April 2025), CSF 2.0 (26 Feb 2024) | documents, not downloaded; which one the plan means is open (section 10) |

## 4. Field mapping to the Event contract

Shares are of all records of the subset. Status: **usable**, **usable with normalisation**, **missing**, **not applicable**.

### 4.1 Precinct6 `signals` and `incident_signals`

| Event field | Source column(s) | Present: signals / incident_signals | Quality notes | Status |
|---|---|---|---|---|
| `event_id` | `artifact_id` | 100% / 100% | Unique in both tables; 0 duplicates | usable |
| `timestamp` | `timestamp` | 100% / 100% | Epoch seconds, UTC. The card: live rows carry "Precinct ingest time"; leads carry the time "Precinct's correlation raised the lead". `event_time` (product time) is only 24.55% / 2.83% present | usable with normalisation |
| `ingested_at` | none | n/a | Set by C2 at parse time (TD-12) | not applicable |
| `event_type` | `message_type` (595 / 21 distinct), `stream_name` (82 / 12) | 100% / 100% | Free product codes; needs C2's vocabulary | usable with normalisation |
| `label.raw_value`, `label.status` | `label_binary` | 100% / 100% | 3 values; mapping in `contracts/label-mapping.json` | usable |
| `label.attack_type` | none | n/a | The only attack-type columns (`mo_name`, `attack_techniques`) are CON-20 columns | missing (null) |
| `host` | `src_host` | 100% / 100% | Sanitised `HOST-NNNN` tokens; `dst_host` only 17.46% / under 0.01% | usable |
| `src_ip` | `src_ip` | valid 33.46% / 100.00% | Live: 60.32% empty, 5.73% host names, 0.49% sentinel `-` (section 6) | usable with normalisation |
| `dst_ip` | `dst_ip` | valid 6.84% / 99.96% | Live: 93.16% empty | usable with normalisation |
| `src_port` | `src_port` | 10.32% / 96.16% | Stored as strings; all present values are 0 to 65535 | usable with normalisation |
| `dst_port` | `dst_port` | 6.37% / 96.14% | As `src_port` | usable with normalisation |
| `protocol` | `protocol` | 5.72% / 99.83% | IANA protocol numbers ("6=TCP, 17=UDP, 1=ICMP", card) | usable with normalisation |
| `user` | `username` | 34.41% / 0.04% | Sanitised `USER-NNNN` tokens | usable |
| `privileged_user` | none | n/a | No column says whether an account is privileged | missing (null) |
| `summary` | none | n/a | Built by C2 | not applicable |
| `provenance.dataset_id` | none | n/a | `precinct6` | usable |
| `provenance.source_file` | file name | 100% | `signals/signals.parquet`, `signals/incident_signals.parquet` | usable |
| `provenance.record_ref` | `artifact_id` | 100% | Unique, so no row number is needed | usable |
| `provenance.source_format` | none | n/a | `parquet` | usable |

**To `extra_fields` (proposed):** `event_time`, `timestamp_source`, `origin`, `org_id` (sanitised token), `pipeline`, `action`, `severity`, `vendor_code`, `product_name`, `vendor_name`, `message_sanitized`, and `src_ip_raw` / `dst_ip_raw` (section 6).

**CON-20 columns, never used as keys or features and never put in `extra_fields`:** `label_binary` (kept only as the dataset label), `incident_ids`, `matched_rules`, `set_roles`, `mo_name`, `suspicion_score`, `label_confidence`, `lifecycle_stage`, `disposition`, `status_name`, `disposition_category`, `is_false_positive`, `attack_techniques`, `attack_tactics`, `defense_techniques`; in the graph, edges of type `INCIDENT_LINK`, every edge `labels.*` column and the edge attributes `incident_id`, `mo_name`, `status`; the node attributes `set_roles`, `suspicion_score`, `incident_ids`, `incident_first_observed`, `incident_last_observed`; all of `graph/attack_reports.*` and all of `graph/incidents.jsonl`. The card's own words for each are in the full profile.

### 4.2 OTRF Windows events (APT29 day 1 and day 2)

| Event field | Source column(s) | Present: day 1 / day 2 | Quality notes | Status |
|---|---|---|---|---|
| `event_id` | none unique | n/a | `RecordNumber` repeats (16,511 / 88,195 duplicate values): it is per log, not global | missing; derived by C2 from dataset, file and line **(proposed)** |
| `timestamp` | `UtcTime` (Sysmon), else `EventTime` | 73.38% / 69.35% (`UtcTime`); 100% (`EventTime`) | Neither carries a zone. `EventTime` is 4.0 h behind `UtcTime`. `@timestamp` (with zone) is the collection time: it follows `EventReceivedTime`, not `EventTime` | usable with normalisation (section 10, Q9) |
| `ingested_at` | none | n/a | Set by C2 | not applicable |
| `event_type` | `Channel` + `EventID` | 100% / 100% | Channel names differ in case: `Security` and `security` both occur (section 6) | usable with normalisation |
| `label.raw_value`, `label.status` | none per event | 0% | Labels are per dataset (section 5) | not applicable: `unlabelled` |
| `label.attack_type` | none per event | 0% | ATT&CK techniques are dataset metadata | missing (null) |
| `host` | `Hostname` | 100% / 100% | Lab host names | usable |
| `src_ip` | `SourceAddress` (Security), `SourceIp` (Sysmon 3) | valid 2.03% / 1.19% | Only network events carry addresses | usable with normalisation |
| `dst_ip` | `DestAddress`, `DestinationIp` | valid 1.63% / 0.64% | As `src_ip` | usable with normalisation |
| `src_port`, `dst_port` | `SourcePort`, `DestPort`, `DestinationPort` | 3.41% / 2.20% (`SourcePort`) | `SourcePortName` and `DestinationPortName` hold sentinels only | usable with normalisation |
| `protocol` | `Protocol` | 3.41% / 2.25% | Protocol numbers | usable with normalisation |
| `user` | `SubjectUserName`, `TargetUserName`, `AccountName`, `User` | 16.24% / 5.95% (`SubjectUserName`) | Several account fields per event; which one is "the" user depends on the event ID | usable with normalisation |
| `privileged_user` | none | n/a | EventID 4672 ("special privileges assigned to new logon") occurs 212 / 235 times; no per-event privilege flag | missing (null) |
| `summary` | none | n/a | Built by C2 | not applicable |
| provenance | `otrf`, zip member name, line number, `json` | 100% | | usable |

The atomic sets have the same columns. In SDWIN-201018195009 the event time column is `TimeCreated` (100%, no zone); `RecordNumber` is unique in SDWIN-200806015757 (506 of 506) but not elsewhere. The Zeek logs: `ts` (epoch, UTC) is present in 100% (day 1) and 49.15% (day 2) of lines; `id_orig_h` / `id_resp_h` carry valid addresses in 60.93% / 46.42% of lines; `uid` repeats across log streams.

**To `extra_fields` (proposed):** `EventID`, `Channel`, `SourceName` (provider), `Task`, `Opcode`, `EventType`, `Severity`, `Image`, `ProcessId`, and the other unmapped scalar fields. There are no CON-20 columns in OTRF.

### 4.3 Loghub (2k samples)

| Event field | Source column(s) | Present | Quality notes | Status |
|---|---|---|---|---|
| `event_id` | `LineId` | 100% in all 16 systems | Unique per file; combine with the system name | usable |
| `timestamp` | per system: `Date`+`Time`, `Time`, `Timestamp` | 100% parsed | 5 systems have no year (Android, Linux, Mac, OpenSSH, Proxifier); only BGL, HPC and Thunderbird are epoch (UTC); the rest have no zone | usable with normalisation (5 systems: missing year) |
| `event_type` | `EventId` (parsed template ID) | 100% | | usable |
| `label` | `Label` (BGL, Thunderbird only) | 100% in those two | Section 5 | usable |
| `host` | `Node` (BGL, HPC), `User` (Mac, Thunderbird) | 98.25% to 100% | | usable |
| `src_ip`, `dst_ip`, ports, `protocol`, `user`, `privileged_user` | none usable | 0% | OpenStack `ADDR` and Mac `Address` are not plain addresses (0% valid) | missing |
| provenance | `loghub-<system>`, file name, `LineId`, `csv` | 100% | | usable |

### 4.4 UNSW-NB15 and CIC-IDS2017

Not profiled yet: the files are not downloaded. The follow-up PR adds the same table. Nothing is assumed about their columns here.

## 5. Labels

**OD-21 rule.** A record without a label becomes `label.status = unlabelled`. A label is never inferred from IPs, hosts, users or how an event looks (FR-41). The mapping from raw values to `flagged` / `unflagged` is in [contracts/label-mapping.json](../contracts/label-mapping.json); values whose meaning is not documented get no status and are quarantined until the team decides (section 10, Q8).

### 5.1 Precinct6 (per record)

| Table | `label_binary` | Count | Share | Proposed status |
|---|---|---|---|---|
| signals | `benign` | 1,897,153 | 94.31% | unflagged |
| signals | `suspicious` | 106,793 | 5.31% | unflagged (proposed; Q7) |
| signals | `malicious` | 7,728 | 0.38% | flagged |
| incident_signals | `malicious` | 238,511 | 100.00% | flagged |

No empty values and no variants. Documented meanings (`precinct6/README.md`, section "Labeling methodology", retrieved 24 Oct 2026):

- `malicious`: "the event is a triggering signal (lead) of a Precinct incident".
- `suspicious`: "the event matched one or more of WitFoo's 261 lead detection rules but is not a lead of any incident."
- `benign`: "no rule matched and the event is not part of any incident."

**Flagged is exactly the set of events that WitFoo's engine linked to incidents.** In `signals`, all 7,728 `malicious` rows have a non-empty `incident_ids` and no `benign` or `suspicious` row has one (7,728 / 7,728). In `incident_signals`, all 238,511 rows are `malicious` and all are linked (238,511 / 238,511).

`suspicious` enters as **unflagged** (proposed): the card says it "is not a lead of any incident". These events become context, are never discarded, and keep `raw_value = "suspicious"` visible to the analyst.

The other label-like columns (`disposition`, `status_name`, `lifecycle_stage`, `mo_name`, scores) are CON-20 columns and are not mapped. `severity` is the source product's severity, not a label: 10 values in `signals`, 49.27% empty, with both `informational` and `Info` present.

### 5.2 OTRF (per dataset)

OTRF has no label field in its events. The ATT&CK mapping is dataset metadata: SDWIN-201018195009 maps to T1003.001 (tactic TA0006); SDWIN-200806015757 maps to T1021.002 (TA0008) (`datasets/atomic/_metadata/*.yaml`). The APT29 techniques come from the emulation plan (section 7.2).

Its events therefore enter as **unlabelled**, with the ATT&CK technique kept as dataset-level metadata, never copied onto each event as a label.

### 5.3 Loghub (per record, two systems)

Documented meaning (`loghub/BGL/README.md` and `loghub/Thunderbird/README.md`, retrieved 24 Oct 2026): "In the first column of the log, "-" indicates non-alert messages while others are alert messages."

| System | `Label` | Count | Proposed status |
|---|---|---|---|
| BGL | `-` | 1,857 | unflagged |
| BGL | `KERNDTLB`, `KERNSTOR`, `APPSEV`, `KERNMNTF`, `KERNTERM`, `KERNREC`, `APPRES`, `APPREAD`, `KERNRTSP`, `APPTO`, `APPCHILD`, `APPOUT` | 60, 30, 17, 11, 7, 5, 4, 3, 2, 2, 1, 1 (143 in total) | flagged |
| Thunderbird | `-` | 2,000 | unflagged |

The individual alert tags are not defined in the README. They are alerts of a supercomputer, not attacks. The other 14 systems have no label in the 2k sample and enter as unlabelled. The README marks HDFS, Hadoop and OpenStack as labelled in their full logs only (separate label files, not downloaded).

### 5.4 UNSW-NB15 and CIC-IDS2017

Not profiled yet. The pages list the label vocabulary without definitions: UNSW-NB15 names nine attack types, "Fuzzers, Analysis, Backdoors, DoS, Exploits, Generic, Reconnaissance, Shellcode and Worms"; CIC-IDS2017 names each attack with its day and time window, and Monday as "Benign (Normal human activities)". These appear in the mapping file with null counts and a pending status until the CSV values are measured.

## 6. Data quality

Effect on ingestion: **reject** (FR-03: no ID or no timestamp, never an Event), **normalise**, **quarantine** (kept aside, not an Event, until a decision), **keep**.

| Issue | Source | Count | Share | Effect on ingestion |
|---|---|---|---|---|
| Host name in an IP field (14 shapes, all host names; 2 are the `aaaa-9999` token shape) | Precinct6 signals `src_ip` | 115,332 | 5.73% | normalise: `src_ip = null`, original in `extra_fields.src_ip_raw`; never resolved or guessed **(proposed)** |
| Empty IP | Precinct6 signals `src_ip` / `dst_ip` | 1,213,345 / 1,874,096 | 60.32% / 93.16% | normalise to null |
| Sentinel `-` in IP | Precinct6 signals `src_ip` | 9,892 | 0.49% | normalise to null |
| Addresses in the RFC 6598 shared space | Precinct6 signals `src_ip` / incident_signals `src_ip` | 499,363 / 173,101 | 24.82% / 72.58% | keep: valid IPs. Probably WitFoo's sanitised replacement for public addresses, but the card does not say so: **unconfirmed** |
| Addresses in the documentation ranges | Precinct6 signals `src_ip` / `dst_ip` | 16,404 / 34,899 | 0.82% / 1.73% | keep (the card's sanitisation maps "public IPs → RFC 5737 TEST-NET") |
| Sanitised tokens (`HOST-NNNN`, `USER-NNNN`, `ORG-NNNN`) | Precinct6 host, user and organisation columns | all values | 100% of present values | keep: consistent tokens across tables (card) |
| Timestamps out of file order | Precinct6 signals / incident_signals `timestamp` | 1,793,271 / 40,291 | 89.14% / 16.89% | keep; correlation sorts by event time |
| Incident times far in the future | Precinct6 `incidents.jsonl` `first_observed_at` / `last_observed_at` | latest in year 2153 / 2226; 12 / 5 not epoch-like | n/a | keep as incident metadata only (not an Event field) |
| Local time without a zone | OTRF `EventTime` (all events) | 196,081 / 587,286 | 100% | normalise: 4.0 h behind `UtcTime`; rule in Q9 **(proposed)** |
| `UtcTime` without a zone marker | OTRF Sysmon events | 143,883 / 407,263 | 73.38% / 69.35% | normalise: read as UTC |
| No unique record ID | OTRF (`RecordNumber` repeats), Zeek (`uid` repeats), Precinct6 embedded leads | 16,511 / 88,195 duplicate `RecordNumber` values | n/a | normalise: `event_id` from dataset + file + line **(proposed)**; never reject |
| Channel name variants | OTRF `Channel`: `Security` and `security` | 28,627 and 12,375 (day 1); 27,207 and 22,854 (day 2) | n/a | keep as written; normalise only for `event_type` |
| Exact duplicate records | OTRF atomic SDWIN-201018195009 / APT29 day 2 Zeek | 9 / 2,399 | 4.89% / 42.36% | keep (provenance differs by line); flag in the evidence |
| Timestamp without a year | Loghub Android, Linux, Mac, OpenSSH, Proxifier | 2,000 each | 100% | quarantine until a year is configured **(proposed)** |
| Timestamp without a zone | Loghub (13 of 16 systems), OTRF | n/a | n/a | normalise with a per-source zone setting |
| Not an address in an address column | Loghub OpenStack `ADDR`, Mac `Address` | 1,845 / 54 | 92.25% / 2.70% | normalise to null |
| Headerless CSV | UNSW-NB15 (documented: column names come from the features file) | not profiled yet | n/a | normalise: names from the features file |
| Encoding and label spelling problems | UNSW-NB15, CIC-IDS2017 | not profiled yet | n/a | quarantine unmapped values (Q8) |
| Encoding problems | Loghub raw logs (0 non-UTF-8 lines); OTRF and Precinct6 JSON lines (0 lines that failed to parse) | 0 | 0% | none |

## 7. Multi-stage attacks and ground truth

Ground truth for evaluating correlation comes from documentation, not from the correlation keys or another correlator's output (correlation design, section 14.1; CON-20, DR-04).

### 7.1 Precinct6: agreement check, not ground truth

The card says (`precinct6/README.md`, "Ground truth and disposition", retrieved 24 Oct 2026): "All labels derive from WitFoo Precinct's automated incident correlation engine — there is no independent, analyst-verified ground truth."

Flagged events are exactly the leads of Precinct incidents (section 5.1). The 51,371 incidents are therefore WitFoo's correlation output:

| Per incident | Measured |
|---|---|
| Linked signal rows (both tables) | median 2, maximum 501; every incident has at least one |
| Embedded leads | median 4, maximum 724 |
| Host-like nodes | 51,295 incidents have more than one |
| ATT&CK tactics (from linked rows) | 51,371 incidents have more than one |
| Time span `first_observed_at` to `last_observed_at` | 25,295 incidents span 0 s; 53 span more than one week |
| Duplicate incidents collapsed by the publisher | 9,204 (listed in `duplicate_incident_ids`) |

The tactics and techniques are themselves derived by WitFoo from the incident (card: "They are priors, not analyst-confirmed per-event attributions"). So Precinct6 incidents are an **agreement check**: they show how often ICD groups events the way WitFoo's engine does. They are not ground truth, and the CON-20 columns (section 4.1) are never used as features or keys.

Open question for the team (Q6): the data plan uses Precinct6 for "ML pair training". Pairs built from Precinct6 incidents would teach a model WitFoo's correlator, not true relatedness.

### 7.2 OTRF APT29: steps documented, not tied to events

| What | Where it comes from |
|---|---|
| Steps 1 to 10 (day 1, 25 sub-steps) and 11 to 20 (day 2, 24 sub-steps), with their names | `adversary_emulation/APT29/Emulation_Plan/Day 1/README.md` and `Day 2/README.md` (attack-arsenal `201db70f`) |
| Stage and technique names per sub-step | `datasets/compound/apt29/emulationplans/apt29.xlsx` (OTRF `d9d40ef1`), columns Stage, Technique(s), Step |
| ATT&CK IDs | xlsx names matched to the ATT&CK 20.0 snapshot: 31 current IDs (day 1), 33 (day 2); 6 older names have no exact match |

Neither file gives step start or end times (0 time values in the xlsx, 0 `hh:mm` strings in the markdown), and no event field marks a step. Steps therefore cannot be tied to events without further work. The OTRF README gives only one timestamp per day. The Zeek and Windows time ranges do not overlap: day 1 Zeek `ts` runs 2020-04-30 00:06 to 00:45 UTC, the Windows events 2020-05-02 02:55 to 03:28 UTC; day 2 Zeek runs 2020-05-01 07:02 to 2020-05-02 02:16, the Windows events 2020-05-02 07:54 to 08:29.

Usable for: technique truth at dataset level, ATT&CK mapping and AI report tests. Not usable yet for pairwise correlation metrics.

### 7.3 UNSW-NB15: ground-truth file, not profiled yet

The page says: "The ground truth table is named UNSW-NB15_GT.csv and the list of event file is called UNSW-NB15_LIST_EVENTS.csv" (retrieved 24 Oct 2026). How many ground-truth rows match records by time and category is measured in the follow-up PR.

### 7.4 CIC-IDS2017: documented attack schedule

The CIC page documents 14 attack windows over four days (4 to 7 July 2017, local lab time), all 14 found verbatim on the saved page. Roles, as documented, without addresses:

| Day | Attacks | Roles |
|---|---|---|
| Tuesday | FTP-Patator, SSH-Patator | 1 attacker, 1 victim web server, through the firewall's NAT |
| Wednesday | DoS slowloris, Slowhttptest, Hulk, GoldenEye; Heartbleed | 1 attacker, 1 victim web server; for Heartbleed 1 victim server |
| Thursday | Web Attack Brute Force, XSS, Sql Injection; Infiltration | 1 attacker, 1 victim web server; Infiltration: 2 victim hosts, then the first victim scans all other clients |
| Friday | Botnet ARES; Port Scan; DDoS LOIT | 1 attacker and 5 victim hosts; 1 attacker and 1 victim server; 3 attackers and 1 victim server |

How many labelled attack flows fall inside their window is measured in the follow-up PR. The script reports two readings (24-hour, and 12-hour without an AM/PM marker), because the hour format of the CSV is not documented and must be checked.

### 7.5 Generated scenarios

Truth by construction: the generator knows which events belong to which attack. This is the primary correlation benchmark (D4). It is not built yet.

## 8. Recommended first development subset (proposed)

Small enough for a laptop:

| Purpose | Subset | Records | Why |
|---|---|---|---|
| CSV ingestion test | UNSW-NB15 (proposed choice, Q1), file `UNSW-NB15_1.csv` | not profiled yet | One headerless file tests the features-file path |
| Correlation development, flagged events | Precinct6 `incident_signals` | 238,511 | All linked to incidents; `src_ip` 100.00% and `dst_ip` 99.96% valid; ports about 96% present |
| Correlation development, context | Precinct6 live `signals` with `timestamp` in [2024-07-29 00:00, 2024-07-30 00:00) UTC | 411,564: 397,315 benign, 10,734 suspicious, 3,515 malicious | All three labels in one timeline; every malicious row in the slice has a valid `src_ip` |
| AI report tests | OTRF APT29 day 1 | 196,081 | Documented steps and techniques |

The two Precinct6 parts are on different timelines: only 43 `incident_signals` rows fall inside the live capture window. `incident_signals` exercises grouping of flagged events; the live slice exercises context attachment.

## 9. Licensing summary

Every source, its licence or terms as written, and its status are in [dataset-licence-register.md](dataset-licence-register.md). Unresolved: OTRF (conflicting: the `LICENSE` file says MIT, the README heading says GPL-3.0), FIRST EPSS (no licence text found), CIRCL vulnerability-cwe-patch (no licence in its card), NVD (terms page not readable without a browser), UNSW-NB15 and CIC-IDS2017 terms to be re-read when the files are downloaded, and which NIST resource the plan means. No dataset record goes in git.

## 10. Open questions and review

### Open questions

Each question has a proposed default that applies until the team decides.

| # | Question | Proposed default | Section |
|---|---|---|---|
| Q1 | Which CSV dataset: UNSW-NB15 or CIC-IDS2017? | UNSW-NB15 (proposed); confirm after both are profiled | 1, 8 |
| Q2 | OTRF licence: MIT (`LICENSE` file) or GPL-3.0 (README heading)? | Unresolved; use for development only, never redistribute OTRF data, cite the repo | 9 |
| Q3 | EPSS licence | Unresolved; use the scores inside ICD, cite FIRST, do not redistribute the snapshot | 9 |
| Q4 | CIRCL vulnerability-cwe-patch licence | Unresolved; not used in Week 1 (not downloaded) | 9 |
| Q5 | Which NIST resource does row 4 mean? | SP 800-61r3 for incident-response wording, CSF 2.0 for control references; confirm with the team | 3.5 |
| Q6 | Precinct6 "ML pair training": pairs from Precinct6 incidents learn WitFoo's correlator | Do not train on Precinct6 incident membership; train on generated scenarios; use Precinct6 only as an agreement check | 7.1 |
| Q7 | Precinct6 `suspicious`: flagged or unflagged? | Unflagged, entering as context, never discarded, raw value visible | 5.1 |
| Q8 | Present but undocumented or ambiguous label values (the contract allows `unlabelled` only when `raw_value` is null) | `status: null`, `decision: pending`; records quarantined until the team decides. Alternative: a contract change (C3) | 5 |
| Q9 | OTRF time zone | Use `UtcTime` where present; otherwise `EventTime` read as UTC−4 (the 4.0 h offset measured in the data); `@timestamp` stays collection time | 4.2 |
| Q10 | A host name in an IP field | `src_ip = null`, original in `extra_fields.src_ip_raw`; never resolved or guessed | 6 |
| Q11 | OTRF and Zeek have no unique ID | `event_id` derived from dataset ID, file and line number; stable across re-ingestion | 4.2 |
| Q12 | Precinct6 attack type: only CON-20 columns hold one | `attack_type = null`; C3's incident type and severity factor fall back to their defaults for Precinct6 | 4.1 |
| Q13 | Loghub timestamps without a year | Quarantine those five systems until a year is configured | 6 |

### Review

| Reviewer | What to check | Status |
|---|---|---|
| Whole team (Thursday review) | Data plan rows and profiling depth (section 1); Q1, Q6, Q7 | pending |
| C3 | Field mapping against the Event contract (section 4); CON-20 columns; Q8 and Q12 | pending |
| AI1 | OTRF and the knowledge-base snapshots for AI reports (sections 3.5, 5.2, 7.2) | pending |
| C1 | Data folder outside the repo; sizes for laptops and CI (sections 2 and 8) | pending |

## 11. Traceability

| Section | Sources |
|---|---|
| 1. Purpose and scope | D4, OD-25 |
| 2. Provenance and versions | FR-05 |
| 3. Inventory per source | FR-02 |
| 4. Field mapping to the Event contract | FR-02, FR-03, FR-04, FR-05, CON-20, NFR-S-07 |
| 5. Labels | OD-21, FR-40, FR-41 |
| 6. Data quality | FR-03, FR-04 |
| 7. Multi-stage attacks and ground truth | CON-20, DR-04, D4 |
| 8. Recommended first development subset | D4, OD-25 |
| 9. Licensing summary | OD-25 |
| 10. Open questions and review | All of the above |
