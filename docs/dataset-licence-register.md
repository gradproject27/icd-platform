# Dataset licence register

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **Owner** | C2, Security Data & Ingestion |
| **Task** | T1-06 (Week 1) |
| **Status** | v1, for team review |
| **Retrieved** | All evidence retrieved on 24 Oct 2026 (UTC); files and pages are in the local data folder and listed with SHA-256 in `c2-profiling/out/sources-*.json` (not committed) |
| **Related** | [dataset-profile.md](dataset-profile.md) (T1-05); [contracts/label-mapping.json](../contracts/label-mapping.json) |

## 1. Rules for this register

- A licence or terms text is quoted by name, verbatim, with its evidence.
- If the licence cannot be verified, the status is **unresolved**. Permission is never assumed.
- **conflicting** means two statements from the same producer disagree.
- **n/a (team-generated)** is data the team makes itself.
- `dataset_id` is the ID used in `contracts/label-mapping.json` and in `Event.provenance.dataset_id`.

## 2. Register

| Source | `dataset_id` | Row | Role | Producer | Licence or terms (verbatim name) | Evidence (retrieved 24 Oct 2026) | Redistribution | Modification | Citation required | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Generated scenarios | `generated-scenarios` | 1 | Primary correlation benchmark; truth by construction; simulated detector for Option B | ICD team | ours | n/a | ours | ours | no | n/a (team-generated) | Not built yet (D4) |
| Precinct6 (small variant) | `precinct6` | 2 | ML pair training; realism and agreement check | WitFoo, Inc. | "Apache License 2.0" (card: "license: apache-2.0") | Hugging Face `witfoo/precinct6-cybersecurity` @ `96311c2e`, `README.md` (card); licence text https://www.apache.org/licenses/LICENSE-2.0 | Allowed: "You may reproduce and distribute copies of the Work or Derivative Works" with the licence's conditions (Apache-2.0, section 4) | Allowed; modified files must carry notices (section 4(b)) | yes: the card's BibTeX (`witfoo_precinct6_2026`, version 2.1.0) | verified | The repo has no separate LICENSE file; the licence is in the card. Labels come from WitFoo's correlation engine (CON-20). The 100M variant is not used |
| OTRF Security Datasets | `otrf` | 3 | Technique truth, ATT&CK mapping, AI report tests | Open Threat Research Forge | `LICENSE`: "MIT License"; README heading: "License: GPL-3.0" | GitHub `OTRF/Security-Datasets` @ `d9d40ef1`, `LICENSE` and `README.md` | MIT: allowed with the notice; GPL-3.0 would add copyleft conditions | as redistribution | no citation text found | conflicting | The README badge also says MIT. The APT29 emulation plan (`mitre-attack/attack-arsenal` @ `201db70f`) is "Apache License", Version 2.0, with "Copyright 2020 The MITRE Corporation" (`NOTICE.txt`) |
| NVD | `nvd` | 4 | Knowledge base for AI reports | NIST | not read | https://nvd.nist.gov/developers/terms-of-use (JavaScript page; the saved HTML has no text) | not verified | not verified | not verified | unresolved | Only one API call (`resultsPerPage=1`); keyless rate limits not read either |
| CISA KEV | `kev` | 4 | Knowledge base for AI reports | CISA | "Creative Commons 0 1.0 License" | GitHub `cisagov/kev-data`, `LICENSE` (branch `main`) | Allowed: "You may use this data in any legal manner" | Allowed | no | verified | The CC0 statement comes from CISA's GitHub repo, not from the KEV catalogue page (it answered 403 to the script). The licence notes that third-party links keep their own terms and that use "does not authorize you to use the CISA Logo or DHS Seal" |
| FIRST EPSS | `epss` | 4 | Knowledge base for AI reports | FIRST EPSS SIG; data by Empirical Security | none found | https://www.first.org/epss/ and https://www.first.org/epss/faq (FAQ: scores are "published freely to the public") | not verified | not verified | not verified | unresolved | "Freely published" is not a licence |
| MITRE ATT&CK enterprise | `attack` | 4 | Knowledge base for AI reports | The MITRE Corporation | "ATT&CK Terms of Use" ("a non-exclusive, royalty-free license to use ATT&CK") | https://attack.mitre.org/resources/legal-and-branding/terms-of-use/; GitHub `mitre-attack/attack-stix-data` @ `c2494b29`, `LICENSE.txt` | Allowed "provided that you reproduce MITRE's copyright designation and this license in any such copy" | Allowed for "research, development, and commercial purposes" | yes: the copyright designation "© 2026 The MITRE Corporation" | verified | ATT&CK 20.0 |
| CIRCL vulnerability-scores | `circl-vulnerability-scores` | 4 | Knowledge base for AI reports | CIRCL | "cc-by-4.0" (card front matter) | Hugging Face `CIRCL/vulnerability-scores` @ `34e6a141`, `README.md` | Allowed with attribution | Allowed with attribution | yes: attribution (CC BY 4.0) | verified | Card only; data not downloaded |
| CIRCL vulnerability-attack-techniques | `circl-vulnerability-attack-techniques` | 4 | Knowledge base for AI reports | CIRCL | "cc-by-4.0" (card front matter) | Hugging Face `CIRCL/vulnerability-attack-techniques` @ `319c3e32`, `README.md` | Allowed with attribution | Allowed with attribution | yes: attribution (CC BY 4.0) | verified | The one CIRCL set downloaded (1,207 rows) |
| CIRCL vulnerability-cwe-patch | `circl-vulnerability-cwe-patch` | 4 | Knowledge base for AI reports | CIRCL | none in the card | Hugging Face `CIRCL/vulnerability-cwe-patch` @ `5f6c8f60`, `README.md` | not verified | not verified | not verified | unresolved | Not downloaded, not used in Week 1 |
| NIST (SP 800-61r3, CSF 2.0) | `nist` | 4 | Knowledge base for AI reports | NIST | NIST copyright statement: information on NIST sites is "public information and may be distributed or copied" | https://www.nist.gov/oism/copyrights; https://csrc.nist.gov/pubs/sp/800/61/r3/final; https://csrc.nist.gov/pubs/cswp/29/the-nist-cybersecurity-framework-csf-20/final | Allowed ("may be distributed or copied") | not stated | requested: "Use of appropriate byline/photo/image credits is requested" | unresolved | The statement is verified, but which NIST resource the plan means is open: to confirm with the team |
| UNSW-NB15 | `unsw-nb15` | 5 | CSV demo and ingestion test; not for detection training | UNSW Canberra (Cyber Range Lab) | "Free use of the UNSW-NB15 dataset for academic research purposes is hereby granted in perpetuity" | https://research.unsw.edu.au/projects/unsw-nb15-dataset | not stated | not stated | yes: "have to cite the above five papers" | verified | Terms verified on the page; data not downloaded yet. "Use for commercial purposes should be agreed by the authors" |
| CIC-IDS2017 | `cic-ids2017` | 5 | CSV demo and ingestion test; not for detection training | Canadian Institute for Cybersecurity, UNB | no named licence; terms: "publicly available for researchers" | https://www.unb.ca/cic/datasets/ids-2017.html | not stated | not stated | yes: "you should cite our related paper" (Sharafaldin, Habibi Lashkari, Ghorbani, ICISSP 2018) | verified | Terms statement only, no named licence. The download form asks for name, e-mail and organisation. Data not downloaded yet |
| Atomic Red Team | `atomic-red-team` | 6 | Lab: only techniques OTRF does not cover | Red Canary, Inc. | "The MIT License" | GitHub `redcanaryco/atomic-red-team`, `LICENSE.txt` (branch `master`) | Allowed with the notice | Allowed | no | verified | No data yet |
| MITRE Caldera | `caldera` | 6 | Lab: only techniques OTRF does not cover | The MITRE Corporation | "Apache License", "Version 2.0, January 2004" | GitHub `mitre/caldera`, `LICENSE` (branch `master`) | Allowed (Apache-2.0, section 4) | Allowed, with notices | no | verified | No data yet |
| Splunk BOTS v1, v2, v3 | `bots` | 7 | Optional second independent source | Splunk | "CC0 1.0 Universal" | GitHub `splunk/botsv1`, `botsv2`, `botsv3`, `LICENSE` and `README.md` | Allowed | Allowed | no | verified | Pre-indexed Splunk data: reading it needs a Splunk Enterprise install with the listed apps. Sizes per README: 6.1 GB (v1), 16.4 GB (v2), 320.1 MB (v3). Not downloaded |
| TON_IoT | `ton-iot` | 8 | Dropped from the critical path | UNSW Canberra | "Free use of the TON_IoT datasets for academic research purposes is hereby granted in perpetuity" | https://research.unsw.edu.au/projects/toniot-datasets | not stated | not stated | yes: "have to cite the above eight papers" | verified | Commercial use "is allowable after asking the author". Its sources do not join into incidents and detection is out of scope |
| LANL Comprehensive, Multi-Source Cyber-Security Events | `lanl` | 9 | Stretch or parser tests | Los Alamos National Laboratory | Waiver: "has waived all copyright and related or neighboring rights" | https://csr.lanl.gov/data/cyber1/ | Allowed | Allowed | requested: "please cite the following paper" (Kent, 2015) | verified | Download form asks for an e-mail address. Files: auth 7.2G, proc 2.2G, flows 1.1G, dns 177M, redteam 4.8K. Not downloaded |
| CERT Insider Threat Test Dataset | `cert` | 9 | Stretch or parser tests | CMU SEI CERT Division with ExactData, LLC (sponsor DARPA I2O) | "CC BY 4.0" | KiltHub (figshare API record 12841247, version 1) | Allowed with attribution | Allowed with attribution | yes: "Lindauer, Brian (2020). Insider Threat Test Dataset" (doi 10.1184/R1/12841247.v1) | verified | Releases r1 to r6.2 plus `answers.tar.bz2` (the answer key). Not downloaded |
| Loghub (2k samples; full logs on Zenodo) | `loghub-bgl`, `loghub-thunderbird` (and the other 14 systems) | 9 | Stretch or parser tests | LOGPAI (CUHK) | `LICENSE`: "The datasets are freely available for research or academic work"; Zenodo record 8196385: "cc-by-4.0" | GitHub `logpai/loghub` @ `dd61d095`, `LICENSE`; Zenodo record 8196385 metadata | Allowed with the condition "refer to the loghub repository URL" and cite | not stated | yes: Zhu et al., "Loghub", ISSRE 2023; "The above license notice shall be included in all copies of the datasets" | verified | Two statements, compatible for research use: the GitHub licence and the Zenodo CC BY 4.0 for the full logs |

## 3. Rules for using the data

- **Datasets never go in git.** `.gitignore` already blocks `data/`, `*.pcap` and `*.evtx`. The data folder lives outside the repo.
- **Only aggregates or synthetic examples go in the repo**: counts, shares, column names, label values with their counts, and quoted documentation. Never records, IP addresses, host names, user names, e-mails or message text from a dataset.
- **Required citations must appear in the final report**: UNSW-NB15 (five papers), CIC-IDS2017 (one paper), TON_IoT (eight papers, if used), CERT, LANL, Loghub, the ATT&CK copyright designation, and Precinct6 (card BibTeX).
- **The 100M Precinct6 variant is not used in Week 1.**
- A source with status **unresolved** or **conflicting** is used for development only. Its data is not redistributed until the question below is closed.

## 4. Open licence questions

| # | Question | Who resolves | Status |
|---|---|---|---|
| L1 | OTRF: MIT (`LICENSE` file) or GPL-3.0 (README heading)? | C2 with the supervisor; ask the OTRF maintainers | pending |
| L2 | FIRST EPSS: what terms apply to the daily scores? | C2 (ask FIRST) | pending |
| L3 | CIRCL vulnerability-cwe-patch: no licence in the card | C2 (ask CIRCL) if the set is ever needed | pending |
| L4 | NVD: terms of use and keyless rate limits (page needs a browser) | C2 | pending |
| L5 | Which NIST resource does row 4 of the data plan mean? | Whole team | pending |
| L6 | UNSW-NB15 and CIC-IDS2017: re-read the terms in the downloaded archives (they may include their own licence files) | C2 (follow-up PR) | pending |
| L7 | Are the academic-use terms of UNSW-NB15, CIC-IDS2017 and TON_IoT enough for a graduation project demo? | Whole team with the supervisor | pending |
