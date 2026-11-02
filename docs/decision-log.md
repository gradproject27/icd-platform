# Decision log (from Week 3)

The ratified decision register (OD-xx, TD-xx, D-xx, 19 Oct 2026) is kept outside the repo. This file records the decisions taken and the numbers measured from Week 3 on, so later work can find them next to the code. One row per decision; the newest entries go at the end of their section.

Status: **proposed** = written down, waiting for the team; **approved** = agreed by the owner named; **ratified** = agreed by the team and added to the register.

## C2: Datasets & Evidence

| ID | Date | Decision or measurement | Status | Evidence |
|---|---|---|---|---|
| W3-D14 (C2 part) | 2 Nov 2026 | The UNSW-NB15 ground-truth file `NUSW-NB15_GT.csv` is in the official download (174,347 rows, 12 columns). Profiled with counts only and matched to the records: 100% of GT rows and 100% of the 321,283 `Label` 1 records match, 0 `Label` 0 records do, and the category agrees on every match. Handed to C3 (Sara) for the ground-truth method (T3-09). | measured | [dataset-profile.md](dataset-profile.md) §7.3; PR #29 |
| W3-D15 (C2 part) | 2 Nov 2026 | The four-file run is for the TD-5 performance budget only. M3 uses `UNSW-NB15_1.csv` (700,001 records, 22,215 flagged). | as in the team plan | [ingestion.md](ingestion.md) §8 |
| TD-5 measurement | 2 Nov 2026 | Parser on all four files: 2,540,047 records in 4 min 17 s (73.2 / 70.8 / 69.4 / 43.9 s), peak memory 130 MB, 0 quarantined. Full upload job with PostgreSQL on file 1: 3 min 49 s, worker peak 188 MB, about 2.4 KB of database per event. GitHub Actions runner, 4 vCPU AMD EPYC 7763, 16 GB RAM. | measured | [ingestion.md](ingestion.md) §8; PR #29 |
| TD-5 budget | 2 Nov 2026 | About twice the measured values: parser ≤ 150 s and ≤ 300 MB per 700,001-line file, ≤ 9 min for all four files; full upload job ≤ 8 min per file with the worker ≤ 400 MB; ≤ 4 KB of database per stored event; 0 quarantined records on the official files. | **proposed** (C2), for team approval | [ingestion.md](ingestion.md) §8 |
| C2-D1 to C2-D4 | 2 Nov 2026 | Evidence package builder: a pure function `build_package(incident, events, created_at)`. It puts in up to 50 events, flagged first in time order, then the context events nearest in time. `truncated` and the counts cover the whole incident. Package ID = `pkg-<incident>-<sha256 of content, 12 hex>`. Every package is masked. | approved (C2) | [evidence-package.md](evidence-package.md); PR #28 |
| C2-D5 | 2 Nov 2026 | Mask tokens are numbered per incident in first-seen order. The style is `host-01`, `ip-01`, `user-01`, not the `HOST-1` the team plan wrote, because the contract, AI1's prompt and AI1's grounding check already use `host-01`. | approved (C2) | PR #28 |
| C2-D6 | 2 Nov 2026 | The masking map is stored in `masking_maps` (migration 0004, numbered in merge order per W3-D2), keyed by package, on the app host only. | approved (C2) | PR #30 |
| C2-D7 | 2 Nov 2026 | The report is stored masked. Only the report API un-masks a display copy (`unmask_report`). | approved (C2) | PR #30 |
| W3-D16 (C2 part) | 2 Nov 2026 | The Precinct6 and OTRF parsers move to Week 5. | as in the team plan | team plan |
