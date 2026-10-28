# Ingestion fixtures (C2, Week 2)

`unsw-nb15-sample.csv`: 30 lines in the UNSW-NB15 flow CSV layout (49 columns, no header, as in `UNSW-NB15_1.csv`). Every value is **invented**: IPs only from the documentation ranges 192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24, times on 22 Jan 2015. No dataset row is in git (NFR-S-07, licence register).

The parser tests (`backend/tests/ingest/`) and the upload test (`backend/tests/jobs/test_unsw_ingest.py`) expect exactly this:

| Lines | Case | Result |
|---|---|---|
| 1 to 5 | Normal flows: dns, http, ftp, hex ports (`0x000b`), no ports (`-`, arp) | unflagged |
| 6 to 18 | Attacks, one or two per category; `" Reconnaissance "` and `" Fuzzers "` with spaces; `Backdoor` and `Backdoors` | flagged, attack type trimmed, variants not merged |
| 19 | Host name `host-a` in `srcip` | unflagged, `src_ip` null, `extra_fields.srcip_raw` |
| 20 | Unknown service `xyz-unknown` | unflagged, `event_type` unknown |
| 21 | Injection-like text in `service` | unflagged, kept as data |
| 22 | Empty `Label` | **unlabelled** |
| 23 | `Label` = `2` | quarantined `unknown_label` |
| 24 | `Label` = `" 1"` (exact match, no trimming) | quarantined `unknown_label` |
| 25 | `Stime` = `not-a-time` | quarantined `bad_timestamp` |
| 26 | `Stime` empty | quarantined `missing_timestamp` |
| 27 | `Stime` = `99` (1970) | quarantined `bad_timestamp` |
| 28 | Empty line | quarantined `empty_record` |
| 29 | 3 columns | quarantined `wrong_column_count` |
| 30 | `sport` = 70000 | unflagged, `src_port` null, `extra_fields.sport_raw` |

Totals: 30 read, 23 events (13 flagged, 9 unflagged, 1 unlabelled), 7 quarantined. Bad bytes, NUL bytes and over-long lines are built inside `test_lines.py` instead, so this file stays plain text.
