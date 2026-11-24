# Demo dataset slice (C2, Week 4; decisions C2-D17 to C2-D19)

The demo uses 86 consecutive-in-time records of the official `UNSW-NB15_1.csv`. **The slice itself is not in git** (dataset rows are never committed: [../ingest/README.md](../ingest/README.md), licence register). What is committed:

| File | Content |
|---|---|
| `unsw-nb15-demo-slice.json` | Manifest: source file SHA-256, the time range, line numbers, counts, slice SHA-256, and the incidents the slice must give (IDs, levels, scores, attack types). No IP, host or user |
| `unsw-nb15-demo-slice.sha256` | The slice's SHA-256 (`sha256sum -c` format) |

**Rule (C2-D17).** Every line of `UNSW-NB15_1.csv` whose `Stime` is in [1421930705, 1421930706] (22 Jan 2015 12:45:05 to 12:45:06 UTC), in file order, unchanged: lines 83,731 to 83,879, 86 lines, 18,312 bytes. `tools/c2/make_demo_slice.py choose` picked it as the shortest range that, uploaded on its own, gives at least one High and one Medium incident (first try).

**What it gives** (checked through the real stack, 24 Nov 2026): 86 events (40 flagged, 46 unflagged, 0 quarantined), 6 incidents: **High 2** (scores 99 and 70, DoS), **Medium 2** (60, Generic), Low 2 (30, Fuzzers). "High-confidence" needs an AI report from a real model, which cannot run until compute is available; with the stub backend all 6 incidents give valid reports.

**Build it and check it:**

```bash
python -I tools/c2/unsw_download.py UNSW-NB15_1.csv --out data/
python tools/c2/make_demo_slice.py rebuild data/UNSW-NB15_1.csv --out demo/   # prints "matches"
```

**Edge cases (C2-D19).** With the stack up (`docker compose up --build --detach --wait`):

```bash
python tools/c2/demo_edge_cases.py demo/unsw-nb15-demo-slice.csv
```

It uploads the slice (86 events, levels as in the manifest), uploads it again (409 `duplicate_upload` naming the first upload), then uploads the slice with three malformed lines appended (3 quarantined: `wrong_column_count`, `empty_record`, `bad_timestamp`; 86 stored). Result on 24 Nov 2026: **ALL PASSED** (GitHub Actions runner, stack built from this branch).
