# Evaluation: ground truth and indicative grouping metrics (UNSW-NB15_1)

Owner: C2 (data and ground truth), for C3's design [correlation-and-risk-design.md](correlation-and-risk-design.md) §14. Decisions C2-D14 to C2-D16 ([decision-log.md](decision-log.md)), approved 24 Nov 2026. **Every number here is indicative**: one file, one ground-truth rule, no tuning. Review requested from C3 (Sara).

## 1. What is measured

Design §14.2 and §14.3, on flagged events only (§14.4, C-17): pairwise precision, recall and F1; incorrect merges (incidents mixing two or more ground-truth incidents); missed groups (ground-truth incidents split over two or more incidents); alert compression (flagged events per incident). Code: `backend/app/evaluation/metrics.py` (counts from the contingency table, so no pair list is built; checked against brute force in `backend/tests/evaluation/test_evaluation.py`).

## 2. Ground-truth method (C2-D14; writes out §14.1)

A **ground-truth incident** is a maximal run of attack records with the **same attack category, the same attacker IP and the same victim IP**, where consecutive records are at most **60 minutes** apart.

| Rule part | Source in the dataset's documentation |
|---|---|
| Attack category | `Attack category` of the official ground-truth file `NUSW-NB15_GT.csv` (= `attack_cat` of the record, 100% agreement, [dataset-profile.md](dataset-profile.md) §7.3) |
| Attacker and victim | `Source IP` and `Destination IP` of the GT file (the testbed's attacker and victim hosts) |
| Time | `Start time` of the GT row (= the record's `Stime`) |

- Read from the flagged events' label and addresses (`backend/app/evaluation/ground_truth.py`), which match the GT file row for row (§7.3: all 174,347 GT rows match, all 321,283 `Label` 1 records are matched, categories agree 100%).
- **No correlation key, window or output is used.** The 60-minute gap is not one of the correlation windows (15 and 30 minutes), and categories are kept apart, which the correlator never does (event type is not a key, design §3).
- Spelling variants stay separate (`Backdoor` and `Backdoors`, C2 decision D5).
- **Known bias.** Attacker and victim together are the same information as the `ip_pair` key, so **recall is expected to be high by construction**. Precision is the informative number: it measures how much the correlator mixes different attacks between the same two hosts. Rejected alternatives: attacker + victim only (would equal the `ip_pair` key, CON-20); same `Attack Name` within 60 minutes (7,226 names, mostly one record each, so it splits real campaigns).
- Sensitivity: the GT gap is also reported at 15 and 240 minutes.

## 3. Run on UNSW-NB15_1.csv (24 Nov 2026)

`python -m app.evaluation.cli unsw-nb15 UNSW-NB15_1.csv --out evaluation` on a GitHub Actions runner (4 vCPU Intel Xeon 6975P-C, Python 3.12): 1 min 25 s, peak 236 MB. Source file SHA-256 `7d851bbe…b511` (168,979,718 bytes), downloaded from the official folder and deleted with the runner. Full output: [evaluation-runs/2026-11-24-unsw-nb15-1/](evaluation-runs/2026-11-24-unsw-nb15-1/) (`evaluation.md`, `evaluation.json`), counts only.

Input: 700,001 events, 22,215 flagged, 22 Jan 2015 11:49 to 19:44 UTC. `correlation-v1`, size cap 500.

**Shipped window (15/30 minutes), GT gap 60 minutes:**

| Predicted | Incidents | GT incidents | Precision | Recall | F1 | Incorrect merges | Missed groups | Alert compression |
|---|---|---|---|---|---|---|---|---|
| As built (with the size cap) | 297 | 295 | 0.479 | 0.041 | 0.076 | 202 | 87 | 74.8 |
| Before the cap (split parts joined) | 40 | 295 | 0.766 | 1.000 | 0.867 | 40 | 0 | 555.4 |

**Sensitivity.** GT gap 15 min: 582 GT incidents, precision 0.450 / 0.760, recall 0.039 / 1.000 (as built / before the cap). GT gap 240 min: 285 GT incidents, precision 0.481 / 0.766, recall 0.042 / 1.000. **Windows 5, 10, 15, 30 and 60 minutes give identical incidents and metrics** on this file: within each attacker–victim pair the attack records are close enough together that the window never cuts a chain. On this file, grouping is decided by the IP pairs and the size cap, not by the window.

## 4. What the numbers say (indicative)

1. **Before the cap, recall is 1.000** (expected, section 2 bias) and **precision 0.766**: the 40 IP-pair groups each mix several attack categories (all 40 groups are incorrect merges). The correlation report shows the same: 155 of 297 incidents carry 4 or more attack types (`many_types` marker).
2. **The size cap is what drops recall to 0.041.** It cuts the 15 groups over 500 links into 272 time-ordered parts (gaps of 1 to 319 s), and each part holds slices of many GT incidents, so most truly related pairs end up in different incidents. It does not improve precision (0.479 vs 0.766), because a time cut does not separate categories.
3. **Alert compression** is 74.8 flagged events per incident as built (22,215 flagged events → 297 alerts).
4. For C3 (W11 tuning, not changed here): splitting by attack category or stage before the time cut would address both points; this is a design choice for C3 and the team.

## 5. Correlation and risk report on the same file

`python -m app.correlation.report unsw-nb15 UNSW-NB15_1.csv` (C3's command, D9), same runner: 1 min 24 s, peak 217 MB. Output: [evaluation-runs/2026-11-24-unsw-nb15-1/report.json](evaluation-runs/2026-11-24-unsw-nb15-1/report.json). This is the real-file run that the roadmap check listed as missing (C3 Step 3 had only a synthetic run).

| Measure | Value |
|---|---|
| Incidents / groups before the cap | 297 / 40 (15 groups split into 272 parts) |
| Links per incident | median 30, p90 402, max 498 |
| Context events linked | 11,289 |
| Risk levels | High 185, Medium 112, Low 0 (scores 48 to 100, median 92) |
| Flags | `asset_unknown` and `outcome_unknown` on all 297 (no asset file given) |

## 6. Reproduce

```bash
python -I tools/c2/unsw_download.py UNSW-NB15_1.csv --out data/   # never commit the file
cd backend
python -m app.evaluation.cli unsw-nb15 ../data/UNSW-NB15_1.csv --out ../evaluation
python -m app.correlation.report unsw-nb15 ../data/UNSW-NB15_1.csv --out ../correlation-report --now 2026-11-24T00:00:00+00:00
```
