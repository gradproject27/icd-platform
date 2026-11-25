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

## NetFlow v3 sample

`nf-v3-sample.csv`: the 55-column NetFlow v3 header and 24 data lines in that layout (NF-UNSW-NB15-v3 and NF-CSE-CIC-IDS2018-v3 share it). Every value is **invented**, with the same IP ranges and day as above; times are epoch milliseconds. `backend/tests/ingest/test_nf_v3.py` reads it as `nf-unsw-nb15-v3` and expects:

| Lines | Case | Result |
|---|---|---|
| 1 | Header | not a record |
| 2 to 5 | Normal flows: HTTP (`L7_PROTO` 7.178), DNS (5, udp), TLS (91.126), ICMP with no application (0) | unflagged |
| 6 to 9 | `Exploits`, `Reconnaissance`, `DoS`, `Backdoor` | flagged |
| 10 | `" Fuzzers "` with spaces | flagged, attack type trimmed |
| 11 | `L7_PROTO` 999.1 (not in the map) | unflagged, `event_type` unknown |
| 12 | Host name `host-a` in `IPV4_SRC_ADDR` | unflagged, `src_ip` null, `extra_fields.IPV4_SRC_ADDR_raw` |
| 13 | `L4_SRC_PORT` = 70000 | unflagged, `src_port` null, `extra_fields.L4_SRC_PORT_raw` |
| 14 | Empty `Label` and `Attack` | **unlabelled** |
| 15 | `Label` = `2` | quarantined `unknown_label` |
| 16 | `Attack` = `Backdoors` (a UNSW-NB15 spelling, not on the NF-v3 list) | quarantined `unknown_attack_type` |
| 17 | `Label` 1 with `Attack` = `Benign` | quarantined `unknown_attack_type` |
| 18 | `Label` 0 with `Attack` = `DoS` | quarantined `label_attack_mismatch` |
| 19 | `FLOW_START_MILLISECONDS` empty | quarantined `missing_timestamp` |
| 20 | `FLOW_START_MILLISECONDS` = `99` (1970) | quarantined `bad_timestamp` |
| 21 | `FLOW_START_MILLISECONDS` = `not-a-time` | quarantined `bad_timestamp` |
| 22 | Empty line | quarantined `empty_record` |
| 23 | 3 columns | quarantined `wrong_column_count` |
| 24 | Injection-like text in `L7_PROTO` | unflagged, `event_type` unknown, kept as data |
| 25 | `PROTOCOL` 47 | unflagged, protocol `gre` |

Totals: 24 read, 15 events (5 flagged, 9 unflagged, 1 unlabelled), 9 quarantined. The NF-CSE-CIC-IDS2018-v3 classes and the header checks are built inside the test file.
