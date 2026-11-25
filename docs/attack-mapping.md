# Dataset labels to MITRE ATT&CK (risk-v1 step 2)

| | |
|---|---|
| **Owner** | C3, Correlation & Risk. Reviewer: Sara (C3) |
| **Decisions** | RV1-D6 (25 Nov 2026), RV1-D8 to RV1-D10 ([decision-log.md](decision-log.md)) |
| **Files** | `backend/app/correlation/attack_maps/*.toml`, loader `backend/app/correlation/attack_mapping.py`, tests `backend/tests/correlation/test_attack_mapping.py` |
| **Status** | Data and checks only. Nothing reads the files yet; risk-v1 (step 6) reads the stages from here instead of `correlation.toml` |

ATT&CK is (c) The MITRE Corporation, used under the ATT&CK Terms of Use ([THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)). The model never chooses a technique, tactic or stage and never sees these files, so grounding check G3 is unchanged.

## 1. ATT&CK version

Pinned to **Enterprise ATT&CK 20.1**, the version in MITRE's `attack-stix-data` repository on 25 Nov 2026 (the project snapshot of 24 Oct is 20.0). Every technique ID in the files was checked in 20.1: present, not revoked, not deprecated, and under the tactic listed. The tactic IDs and names are P4's `tactics.toml` (TA0005 is "Stealth", TA0112 "Defense Impairment").

## 2. Tactic to stage

`attack_maps/tactic-stages.toml`. An attack type's stage is the **highest** stage among its tactics.

| Stage | Name (`correlation.toml`) | Tactics |
|---|---|---|
| 1 | reconnaissance | TA0043 Reconnaissance, TA0042 Resource Development, TA0007 Discovery |
| 2 | exploitation | TA0001 Initial Access, TA0002 Execution, TA0006 Credential Access |
| 3 | installation | TA0003 Persistence, TA0004 Privilege Escalation, TA0005 Stealth, TA0112 Defense Impairment, TA0011 Command and Control |
| 4 | propagation | TA0008 Lateral Movement |
| 5 | actions on objectives | TA0009 Collection, TA0010 Exfiltration, TA0040 Impact |

## 3. Mapping quality

| Quality | Meaning | Rule checked by the loader |
|---|---|---|
| `exact` | The label names one technique | At least one tactic and technique; stage = rule of section 2 |
| `partial` | The label covers several techniques; the main one is given | Same |
| `category-only` | The name implies no certain tactic | No tactic or technique; the stage is kept from `correlation.toml` (decision of 25 Nov 2026) |

## 4. Tables

### UNSW-NB15 (`unsw-nb15.toml`; also NF-UNSW-NB15-v3)

The tactics equal P4's `tactics.toml` (a test keeps them equal). UNSW-NB15 publishes only category names, so most rows are `partial`.

| Label | Technique(s) | Tactic(s) | Stage | Quality |
|---|---|---|---|---|
| Reconnaissance | T1595 Active Scanning | TA0043 | 1 | partial |
| Fuzzers | T1595.002 Vulnerability Scanning | TA0043 | 1 | partial |
| Analysis | — | — | 1 | category-only |
| Generic | — | — | 2 | category-only |
| Exploits | T1190 Exploit Public-Facing Application | TA0001 | 2 | partial |
| Shellcode | T1203 Exploitation for Client Execution | TA0002 | **2** (today 3) | partial |
| Backdoors, Backdoor | T1505 Server Software Component; T1071 Application Layer Protocol | TA0003, TA0011 | 3 | partial |
| Worms | T1210 Exploitation of Remote Services | TA0008 | 4 | partial |
| DoS | T1498 Network Denial of Service | TA0040 | 5 | partial |

Against today's `correlation.toml` stages, only **Shellcode** changes (3 to 2, decision of 25 Nov 2026: follow ATT&CK). A test records this, so step 6 makes the change knowingly.

### NF-CSE-CIC-IDS2018-v3 (`nf-cse-cic-ids2018-v3.toml`)

Class names as printed on the [UQ NetFlow dataset page](https://staff.itee.uq.edu.au/marius/NIDS_datasets/); the CSV spelling is **not verified yet** (section 5). What each class covers: the [CSE-CIC-IDS2018 page](https://unb.ca/cic/datasets/ids-2018.html).

| Label | Covers | Technique(s) | Tactic(s) | Stage | Quality |
|---|---|---|---|---|---|
| BruteForce | FTP-Patator, SSH-Patator | T1110.001 Password Guessing | TA0006 | 2 | exact |
| Web Attacks | DVWA brute force, XSS, SQL injection | T1190 Exploit Public-Facing Application | TA0001 | 2 | partial |
| Infiltration | Malicious file from a download, then internal scanning | T1204.002 Malicious File; T1046 Network Service Discovery | TA0002, TA0007 | 2 | partial |
| Bot | Zeus, Ares | T1071 Application Layer Protocol | TA0011 | 3 | partial |
| DoS | Hulk, GoldenEye, Slowloris, Slowhttptest | T1499.002 Service Exhaustion Flood | TA0040 | 5 | partial |
| DDoS | LOIC (HTTP, UDP), HOIC | T1498 Network Denial of Service; T1499 Endpoint Denial of Service | TA0040 | 5 | partial |

### OTRF (`otrf.toml`)

The technique comes from each dataset's own metadata, so the rows are `exact`. APT29 day 1 and 2 are mapped per emulation-plan step. The OTRF parser (step 3b, [ingestion.md](ingestion.md) §10) keeps every event unlabelled; the technique is joined by dataset in step 6, because the plan's steps carry no times.

| Dataset | Technique | Tactic | Stage |
|---|---|---|---|
| SDWIN-201018195009 (LSASS dump) | T1003.001 LSASS Memory | TA0006 | 2 |
| SDWIN-200806015757 (SMB copy) | T1021.002 SMB/Windows Admin Shares | TA0008 | 4 |

## 5. Flow datasets for the classifier (RV1-D10)

The classifier of risk-v1 trains on the **NetFlow v3** versions of UNSW-NB15 and CSE-CIC-IDS2018 from the University of Queensland, which share 53 features ([dataset page](https://staff.itee.uq.edu.au/marius/NIDS_datasets/); Luay et al., "Temporal Analysis of NetFlow Datasets for Network Intrusion Detection Systems", [arXiv 2503.04404](https://arxiv.org/abs/2503.04404)):

| Dataset | Flows | Attack share | Classes | DOI |
|---|---|---|---|---|
| NF-UNSW-NB15-v3 | 2,365,424 | about 5.4% | 9 | 10.48610/6e0eda1 |
| NF-CSE-CIC-IDS2018-v3 | 20,115,529 | 12.93% | 6 | 10.48610/ece9b83 |

Why not the original CIC files: CIC-IDS2017 has more than 25% artefact flows and IP-and-time-window labelling ([Engelen et al. 2021](https://lirias.kuleuven.be/retrieve/713070)); CSE-CIC-IDS2018 was built with the same flow tool, and its processed CSVs appear to lack source and destination IPs ([COMIDDS](https://fkie-cad.github.io/COMIDDS/content/datasets/cse_cic_ids2018)). The NF-v3 files were re-extracted from the PCAPs with nProbe and labelled "by comparing the precise timestamps and 5-tuple identifiers" with the original ground truth (arXiv 2503.04404, §4.2).

The original UNSW-NB15 CSVs stay for the existing demo, correlation evaluation and ground truth. NF-UNSW-NB15-v3 is a different flow extraction (127,693 attack flows by the per-class counts on the dataset page, against 321,283 attack records in the original).

**Header check: done 25 Nov 2026.** The user downloaded both files in a browser and checked line 1: the same 55 columns in both, from `FLOW_START_MILLISECONDS` to `Label`, `Attack` (53 features plus the two label columns). The parser (step 3a, [ingestion.md](ingestion.md) §9) requires exactly this header. Row counts and class spellings are still to be measured by the first `python -m app.ingest.cli <dataset_id> <file> --profile` run; until then the class names are the dataset page's.
