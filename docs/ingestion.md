# Ingestion: parser, normalizer, labels and quarantine (C2, Week 2)

Owner: **C2**. How an uploaded file becomes `Event` records (contracts v1) or quarantined records, and how the intake summary is counted. Plan: "ICD Week 2 Detailed Plan", section 5. Decisions: C2 Week 2 D1 to D14 (proposed, team to confirm).

## 1. Where it runs

C1's worker calls one parser per dataset (`docs/api-upload-jobs.md` section 5, accepted by C2 as written):

```python
parse(path: Path, context: IntakeContext) -> Iterator[Event | Quarantined]
```

- One item per record read, in file order. One bad record never raises; `ParseError` only when the whole file cannot be read.
- The parser never writes to the database. The worker stores events in `events` and the rest in `quarantined_records` (C1 migration `0002`), and counts both into `IntakeCounts`.
- Parsers are registered by `dataset_id` in `backend/app/ingest/registry.py`. Week 2: `fixture` (C1) and **`unsw-nb15`** (C2). Risk-v1 step 3a: **`nf-unsw-nb15-v3`** and **`nf-cse-cic-ids2018-v3`** (section 9); step 3b: **`otrf`** (section 10); step 3c: **`precinct6`** (section 11).

| Module (`backend/app/ingest/`) | Job |
|---|---|
| `unsw_nb15.py` | UNSW-NB15 parser and the aggregate-only profile |
| `nf_v3.py` | NetFlow v3 parser (both UQ NF-v3 datasets) and its aggregate-only profile |
| `otrf.py` | OTRF Windows event parser and its aggregate-only profile |
| `precinct6.py` | Precinct6 signal parser (JSON lines) and its aggregate-only profile |
| `precinct6_export.py` | Export a Precinct6 Parquet slice to JSON lines for upload (needs pyarrow) |
| `normalize.py` | Pure value normalizers (time, IP, port, protocol, numbers, IDs) |
| `labels.py` | Label mapping from `contracts/label-mapping.json` |
| `event_types.py` | `event_type` vocabulary from `contracts/event-types.json` |
| `lines.py` | Untrusted line reader; `read_original` for the original-record link |
| `evidence.py` | `Event` to `EvidenceEvent` for AI1 (no masking yet) |
| `cli.py` | Run a parser on a local file and print the intake summary and time |
| `mappings/` | Copies of the two contracts files (the Docker image only holds `backend/app`); a test fails when they differ |

## 2. Intake summary

| Plan wording | `IntakeCounts` field |
|---|---|
| records read | `records_read` |
| normalized | `events_stored` |
| labelled | `flagged + unflagged` |
| unlabelled | `unlabelled` |
| quarantined | `quarantined`, by reason in `quarantined_by_reason` |

`flagged + unflagged + unlabelled = events_stored` and `events_stored + quarantined = records_read`, checked by the contract and against the tables by the worker, so no record disappears. A header line is not a record and is not counted. Without the stack:

```
cd backend
python -m app.ingest.cli unsw-nb15 <path>/UNSW-NB15_1.csv          # summary + time
python -m app.ingest.cli unsw-nb15 <path>/UNSW-NB15_1.csv --json
```

## 3. UNSW-NB15 field mapping

Headerless CSV, 49 columns in the order of `NUSW-NB15_features.csv` (column 44 is spelled `ct_src_ ltm` there; the space is dropped).

| Event field | Source | Rule |
|---|---|---|
| `event_id` | none in the data | `unsw-nb15:<file stem>:<line>`, stem cut to `[A-Za-z0-9._-]`, at most 60 characters. Same file name, same IDs on re-ingestion (D7) |
| `timestamp` | `Stime` | Epoch seconds, UTC. Empty: `missing_timestamp`; not a number or outside 1990 to 2100: `bad_timestamp` |
| `ingested_at` | none | `IntakeContext.ingested_at`, the same for the whole file |
| `event_type` | `service` | Vocabulary in section 4. Never from `attack_cat` or `Label` |
| `label.raw_value`, `label.status` | `Label` | Exact match in the label mapping: `1` flagged, `0` unflagged (proposed). Empty: unlabelled |
| `label.attack_type` | `attack_cat` | Spaces trimmed; empty: null. Variants such as `Backdoor` and `Backdoors` are kept apart |
| `host` | none | null: the data has no host names and none is invented (D8, open) |
| `src_ip`, `dst_ip` | `srcip`, `dstip` | Canonical IP text; not an IP: null, original in `extra_fields.srcip_raw` / `dstip_raw` |
| `src_port`, `dst_port` | `sport`, `dsport` | Decimal or hex (`0x000b`); `-`, empty or outside 0 to 65535: null, original in `extra_fields.sport_raw` / `dsport_raw` |
| `protocol` | `proto` | Lower case; `-`: null |
| `user`, `privileged_user` | none | null |
| `summary` | `proto`, `service`, `state`, `dur`, `sbytes`, `dbytes` | For example `tcp flow, service http, state FIN, 0.04 s, 1,256 B out, 8,420 B in`. **Never an IP, host or user** (section 6) |
| `provenance` | | `dataset_id` from the upload, `source_file` = uploaded file name, `record_ref` = `<file name>:<line>`, `source_format` = `csv` |
| `extra_fields` | the other 41 columns | Numbers as int or float, `-` and empty as null. `Label` and `attack_cat` are never copied here |

## 4. Event type vocabulary

`contracts/event-types.json` is the list C2 publishes (contracts v1, open question 1). Types: `network_flow`, `http_request`, `dns_query`, `ftp_session`, `ftp_data_transfer`, `smtp_session`, `pop3_session`, `ssh_session`, `tls_session`, `snmp_request`, `irc_session`, `radius_request`, `dhcp_request`, `unknown`. Each source maps one activity column; a value not in the map is `unknown`. C3's fixture names (`network_scan`, `fuzzing`, ...) are placeholders, not part of this list. Step 3b adds 34 Windows event types for OTRF (`process_creation`, `network_connection`, `logon_success`, `process_access`, `registry_change`, `powershell_script_block` and others; the full list and the `Channel:EventID` keys are in the file).

## 5. Quarantine reason codes

Every quarantined record keeps `record_ref` (file and line), the reason in plain words and the first 500 characters of the line (NUL bytes replaced).

| Code | When |
|---|---|
| `empty_record` | The line is empty or only spaces |
| `bad_encoding` | The line is not UTF-8, or holds a NUL byte |
| `line_too_long` | The line is longer than 64 KiB (the rest of the line is skipped, the next line is read) |
| `bad_csv` | The CSV reader rejects the line |
| `wrong_column_count` | Not 49 columns (UNSW-NB15) or 55 columns (NetFlow v3) |
| `missing_timestamp` | `Stime` (UNSW-NB15) or `FLOW_START_MILLISECONDS` (NetFlow v3) is empty, or an OTRF event has no `UtcTime`, `EventTime` or `TimeCreated` |
| `bad_timestamp` | `Stime` is not epoch seconds, or `FLOW_START_MILLISECONDS` is not epoch milliseconds, or the time is outside 1990 to 2100 |
| `unknown_label` | The label value is not in the label mapping (rule `unknown_value`) |
| `pending_label` | The label value is listed with a pending decision (rule `pending_values`) |
| `unknown_attack_type` | NetFlow v3 only: `Label` is 1 and `Attack` is not a spelling the label mapping lists for the dataset (never guessed) |
| `label_attack_mismatch` | NetFlow v3 only: `Label` is 0 but `Attack` is neither `Benign` nor empty |
| `bad_json` | OTRF and Precinct6: the line is not valid JSON |
| `not_an_object` | OTRF and Precinct6: the line is JSON but not an object |
| `missing_record_id` | Precinct6 only: `artifact_id` is empty |
| `unknown_time_zone` | OTRF only: the event has only a local time and the file gives no single offset to UTC (section 10) |
| `invalid_event` | The built Event fails the contract (should not happen; kept as a safety net) |
| `duplicate_event_id` | Set by the worker (C1): the same `event_id` appeared earlier in the file |

## 6. Original record, evidence and masking

- **Original record link (FR-05).** Every Event and quarantined record has `record_ref` = `<file name>:<line>`. The worker keeps the uploaded file as `/data/uploads/<upload_id>`, so `read_original(path, record_ref)` returns the line. `python -m app.ingest.cli unsw-nb15 <file> --show-record UNSW-NB15_1.csv:42` prints it (it can hold real IPs: use it locally only). A dashboard endpoint is a Week 3 item for C1.
- **Evidence package (with AI1).** The contract is `EvidencePackage` (frozen). `evidence_event(event, role)` fills an `EvidenceEvent` from an Event: event ID, timestamp, event type, role, label status, attack type, the four entity fields, summary, and `source` = `record_ref`. Up to 50 events per incident (OD-03).
- **Masking is Week 3.** Because summaries never hold entities, the masker only has to replace `host`, `src_ip`, `dst_ip` and `user` with tokens and set `masked = true`. Until then C1's handoff refuses the package (`unmasked_evidence`).

## 7. Untrusted input

Lines are read as bytes with a 64 KiB limit, decoded strictly, and parsed one at a time (a stray quote cannot swallow the next lines). Injection-like text stays data: it is stored through bound parameters and never builds a type or a key. Full hostile-input work is Week 7.

## 8. Determinism and speed

Same file and same `ingested_at` give the same items (`test_deterministic`). Measured on a 700,000-line synthetic file in the UNSW layout (126 MB): about 90 s for the parser alone, and 4 min 16 s for the whole upload job (parse, store in PostgreSQL in batches of 1,000, check the counts) on the development container. 

**Real file, 31 Oct 2026.** `python -m app.ingest.cli unsw-nb15 UNSW-NB15_1.csv` (parser and intake counting, no database) on a GitHub Actions runner (4 vCPU Intel Xeon Platinum 8573C, 15 GB RAM, Python 3.12):

| File | Bytes | Records read | Normalized | Labelled (flagged / unflagged) | Unlabelled | Quarantined | Time | Records/s |
|---|---|---|---|---|---|---|---|---|
| `UNSW-NB15_1.csv` | 168,979,718 | 700,001 | 700,001 | 700,001 (22,215 / 677,786) | 0 | 0 | 52.2 s (second run 52.6 s) | 13,405 |

labelled + unlabelled + quarantined = records read.

**All four files, time and peak memory (T3-05), 2 Nov 2026.** Same command under `/usr/bin/time -v` on a GitHub Actions runner (4 vCPU AMD EPYC 7763, 16 GB RAM, Python 3.12; slower per core than the 31 Oct runner, so file 1 took 73 s here instead of 52 s). The files were downloaded on the runner and deleted with it.

| File | Records read | Flagged / unflagged | Quarantined | Time | Records/s | Peak memory (RSS) |
|---|---|---|---|---|---|---|
| `UNSW-NB15_1.csv` | 700,001 | 22,215 / 677,786 | 0 | 73.2 s | 9,566 | 130 MB |
| `UNSW-NB15_2.csv` | 700,001 | 52,749 / 647,252 | 0 | 70.8 s | 9,893 | 129 MB |
| `UNSW-NB15_3.csv` | 700,001 | 157,425 / 542,576 | 0 | 69.4 s | 10,088 | 129 MB |
| `UNSW-NB15_4.csv` | 440,044 | 88,894 / 351,150 | 0 | 43.9 s | 10,034 | 83 MB |
| **All four** | **2,540,047** | **321,283 / 2,218,764** | **0** | **257.2 s (4 min 17 s)** | **9,876** | **130 MB** (one file at a time) |

Memory does not grow with the file: the parser streams line by line, and the peak is the Python process plus the duplicate-ID set of one file.

**Full upload job with PostgreSQL, file 1.** `docker compose up --build`, then `POST /uploads` with `UNSW-NB15_1.csv` straight to the API, on the same runner:

| Step | Result |
|---|---|
| Upload (169 MB, stored and hashed) | 0.6 s |
| Upload to job `done` (parse, store in batches of 1,000, check counts) | 228.6 s (3 min 49 s); job ran 3 min 47 s |
| Counts | 700,001 read and stored (22,215 flagged, 677,786 unflagged), 0 quarantined |
| Peak memory (cgroup `memory.peak`) | worker 188 MB; api 415 MB; db 3.07 GB (includes PostgreSQL's file cache) |
| Database size after the job | 1,613 MB for 700,001 events (about 2.4 KB per event) |

The job takes about 3.1 times the parser alone; the extra is PostgreSQL inserts.

**TD-5 budget (proposed by C2, 2 Nov 2026; for team approval).** About twice the measured values, rounded, so normal runner differences pass (decision C2-D9). Measured on a 4 vCPU runner; a slower laptop may need more.

| Measure | Measured | Proposed budget |
|---|---|---|
| Parser, one 700,001-line file | 73 s, 130 MB | ≤ 150 s and ≤ 300 MB |
| Parser, all four files (2.54 M records) | 4 min 17 s, 130 MB | ≤ 9 min and ≤ 300 MB |
| Full upload job, one 700,001-line file | 3 min 49 s; worker 188 MB | ≤ 8 min; worker ≤ 400 MB |
| Database per stored event | 2.4 KB | ≤ 4 KB (all four files ≈ 6 GB of disk) |
| Quarantined records on the official files | 0 | 0 (any quarantine on these files is a bug to look at) |

## 9. NetFlow v3 field mapping (risk-v1 step 3a)

Datasets `nf-unsw-nb15-v3` and `nf-cse-cic-ids2018-v3` (University of Queensland, [dataset page](https://staff.itee.uq.edu.au/marius/NIDS_datasets/)) share one parser, `nf_v3.py`, because their header is the same. Their role is classifier training and calibration for the risk-v1 confidence (decision RV1-D10), not the correlation demo.

**Header.** Line 1 must be exactly the 55 column names, from `FLOW_START_MILLISECONDS` to `Label`, `Attack` (checked by the user in both files on 25 Nov 2026). Any other first line stops the file with a parse error, because every column is read by its position. A demo slice of the 20.1M-flow CIC file must keep this line, for example `head -n 50001 NF-CSE-CIC-IDS2018-v3.csv > slice.csv`.

| Event field | Source | Rule |
|---|---|---|
| `event_id` | none in the data | `<dataset_id>:<file stem>:<line>`, as for UNSW-NB15 |
| `timestamp` | `FLOW_START_MILLISECONDS` | Epoch milliseconds, UTC. Empty: `missing_timestamp`; not a number or outside 1990 to 2100: `bad_timestamp` |
| `event_type` | `L7_PROTO` | nDPI `<master id>.<app id>`; only the master ID is looked up (`contracts/event-types.json`): 0 `network_flow`, 1 `ftp_session`, 175 `ftp_data_transfer`, 2 `pop3_session`, 3 `smtp_session`, 5 `dns_query`, 7 `http_request`, 14 `snmp_request`, 18 `dhcp_request`, 65 `irc_session`, 91 `tls_session`, 92 `ssh_session`, 146 `radius_request`; anything else `unknown`. Never from `Label` or `Attack` |
| `label.raw_value`, `label.status` | `Label` | Exact match: `1` flagged, `0` unflagged (proposed, as UNSW-NB15). Empty: unlabelled; other values: `unknown_label` |
| `label.attack_type` | `Attack` | Spaces trimmed. Only on `Label` 1, and only a spelling listed in `attack_type_values` of the label mapping, else `unknown_attack_type`. On `Label` 0, `Attack` must be `Benign` or empty, else `label_attack_mismatch` |
| `src_ip`, `dst_ip` | `IPV4_SRC_ADDR`, `IPV4_DST_ADDR` | As UNSW-NB15; not an IP: null, original in `extra_fields.IPV4_SRC_ADDR_raw` / `IPV4_DST_ADDR_raw` |
| `src_port`, `dst_port` | `L4_SRC_PORT`, `L4_DST_PORT` | As UNSW-NB15; original in `extra_fields.L4_SRC_PORT_raw` / `L4_DST_PORT_raw` |
| `protocol` | `PROTOCOL` | IANA number to name: 1 icmp, 2 igmp, 6 tcp, 17 udp, 47 gre, 50 esp, 51 ah, 58 ipv6-icmp, 132 sctp; other numbers kept as their text |
| `host`, `user`, `privileged_user` | none | null |
| `summary` | `PROTOCOL`, `L7_PROTO`, `FLOW_DURATION_MILLISECONDS`, `IN_BYTES`, `OUT_BYTES` | For example `tcp flow, L7 7.178, 120 ms, 1,256 B src to dst, 8,420 B dst to src`. Never an IP, host or user |
| `extra_fields` | the other 47 columns | Numbers as int or float; `L7_PROTO` kept as text (`7.178` must not become a float). `Label` and `Attack` are never copied here |

**Not measured yet.** Class spellings come from the dataset page, and the L7 master IDs from nDPI's `ndpi_protocol_ids.h`. The first run of `python -m app.ingest.cli <dataset_id> <file> --profile` on each real file prints the counts of `Label`, `Attack`, (`Label`, `Attack`) pairs, `PROTOCOL` and L7 master IDs (no IP or port), and the label mapping counts are filled from it. A spelling seen there but not listed is added to the mapping by a reviewed change, never accepted silently.

## 10. OTRF field mapping (risk-v1 step 3b)

Dataset `otrf`, parser `otrf.py`. Input: the JSON-lines file inside an OTRF zip (unzip first; uploads take `.json`), one Windows event per line: APT29 day 1 (`apt29_evals_day1_manual_*.json`, 385 MB), APT29 day 2 (1.7 GB: larger than the 512 MB upload limit, so upload it in line slices, each line is independent) and the atomic sets. The Zeek logs are another format and are not read. Role: ATT&CK technique ground truth (RV1-D5), not the classifier.

**Label.** None per event: every event is `unlabelled` with no attack type. The technique is dataset metadata (`label_scope` `per_dataset`; `backend/app/correlation/attack_maps/otrf.toml`) and is joined to events by dataset, not by any event field, in step 6. APT29 emulation-plan steps carry no times (dataset profile section 7.2), so steps cannot be tied to single events yet.

**Event time.** In order:

1. `UtcTime` (Sysmon events; UTC by definition, no zone written).
2. Otherwise the local time `EventTime` (or `TimeCreated` in some atomic sets), minus the file's offset. Before parsing, the parser reads the file once and computes local minus `UtcTime` (rounded to 15 minutes) on every event that has both. If all of them agree, that offset is used; if they disagree or there is no such event, the event is quarantined `unknown_time_zone`, never guessed. `extra_fields.timestamp_source` and `utc_offset_minutes` record what was used.

Measured on 25 Nov 2026: APT29 day 1, -240 minutes in 143,883 of 143,883 pairs (event times 2020-05-02 02:55 to 03:28 UTC, as in the dataset profile); SMB atomic set, -240 in 412 of 412; LSASS atomic set, -960 in 148 of 148 (its `TimeCreated` is a 12-hour clock without AM or PM, so a fixed UTC-4 rule would have been 12 hours wrong). `@timestamp` is the collection time, not the event time, and is only kept in `extra_fields`.

| Event field | Source | Rule |
|---|---|---|
| `event_id` | none unique (`RecordNumber` repeats) | `otrf:<file stem>:<line>` |
| `event_type` | `Channel` + `EventID` | Key `<channel in lower case>:<EventID>` in `contracts/event-types.json` (so `Security` and `security` map alike); 67 keys; other keys `unknown` |
| `host` | `Hostname` | As written; `-` is null. The NXLog field `host` is the collector, not the event's host, and stays in `extra_fields` |
| `src_ip`, `dst_ip` | `SourceAddress` / `DestAddress` (Security), `SourceIp` / `DestinationIp` (Sysmon) | As written by Windows; not an IP: null and `<field>_raw`. For Security 5156 the direction is in `extra_fields.Direction` |
| `src_port`, `dst_port` | `SourcePort`, `DestPort` / `DestinationPort` | 0 to 65535, else null and `<field>_raw` |
| `protocol` | `Protocol` | IANA number to name (`6` tcp, `17` udp, ...); Sysmon's `tcp` kept |
| `user` | `TargetUserName` for logon and credential events (4624, 4625, 4634, 4647, 4648, 4768, 4769, 4776), else `SubjectUserName`, else `User` | All account fields also stay in `extra_fields` |
| `privileged_user` | EventID 4672 | `true` on 4672 ("Special privileges assigned to new logon"); null on every other event (the data does not say) |
| `summary` | event type, channel, EventID, program file name | For example `process creation (Microsoft-Windows-Sysmon/Operational 1), program tool.exe`. Only the program's file name, never its folder (folders can hold a user name). Never an IP, host or user |
| `provenance` | | `source_format` = `json`, `record_ref` = `<file name>:<line>` |
| `extra_fields` | every other field | Scalars kept; lists and objects as JSON text; text longer than 4,000 characters cut (script blocks) |

**Real files, 25 Nov 2026** (development container, 4 vCPU, Python 3.13; files downloaded from the public `OTRF/Security-Datasets` repository and not committed): APT29 day 1, 196,081 lines read, 196,081 events, 0 quarantined, 3,902 events with an unmapped type (mostly Security 5447 and 4627), 13.5 s including the offset pass. LSASS atomic set 184 / 184 and SMB atomic set 506 / 506, 0 quarantined. Run `python -m app.ingest.cli otrf <file> --profile` for counts by type, time field and offset (no host, user, IP or message).

## 11. Precinct6 field mapping (risk-v1 step 3c)

Dataset `precinct6`, parser `precinct6.py`. Role: agreement check against WitFoo's own correlation engine (RV1-D5, CON-20); never ground truth, never training data.

**Input.** Precinct6 ships Parquet (`signals/signals.parquet`, 2,011,674 rows; `signals/incident_signals.parquet`, 238,511 rows). Uploads take text files, so export a slice to JSON lines first (needs `pip install -r requirements-dev.txt` for pyarrow):

```
cd backend
python -m app.ingest.precinct6_export <dir>/signals/incident_signals.parquet --out leads.jsonl
python -m app.ingest.precinct6_export <dir>/signals/signals.parquet --out live-2024-07-29.jsonl \
    --start 2024-07-29T00:00:00Z --end 2024-07-30T00:00:00Z
```

These are the dataset profile's two slices (section 8): 238,511 leads, and 411,564 live signals of 29 Jul 2024 UTC. The export keeps every column unchanged; datetime columns become epoch seconds. A Parquet file uploaded as is fails with a parse error that names this command. The exported files hold real rows: never commit them.

| Event field | Source | Rule |
|---|---|---|
| `event_id` | `artifact_id` | `precinct6:<artifact_id>` (unique in both tables, so stable across slices). Empty: `missing_record_id` |
| `timestamp` | `timestamp` | Epoch seconds, UTC. The card says it is Precinct's ingest time (live rows) or the time a lead was raised; product time `event_time` (often empty) stays in `extra_fields` |
| `event_type` | `message_type` | Map in `contracts/event-types.json`, **empty for now**: every event is `unknown` until a profile run lists the codes (595 in signals) and a reviewed change maps them. Never from `label_binary` or a CON-20 column |
| `label` | `label_binary` | `malicious` flagged; `benign` and `suspicious` unflagged (`suspicious` stays visible as the raw value). Missing: unlabelled; other values: `unknown_label`. `attack_type` null (profile Q12) |
| `host` | `src_host` | Sanitised `HOST-NNNN` token; `dst_host` stays in `extra_fields` |
| `src_ip`, `dst_ip` | `src_ip`, `dst_ip` | Empty or `-`: null. A host name in an IP column: null, original in `<column>_raw` |
| `src_port`, `dst_port`, `protocol` | same names | Ports 0 to 65535; protocol IANA number to name |
| `user` | `username` | Sanitised `USER-NNNN` token |
| `privileged_user` | none | null |
| `summary` | `stream_name`, `message_type`, `product_name`, `action` | For example `Precinct6 signal: stream Firewall, type fw_allow, product ExampleFW, action allow`. Never an IP, host or user |
| `extra_fields` | the other columns | Lists and objects as JSON text, long text cut at 4,000 characters |
| (dropped) | the 15 CON-20 columns | `label_binary` (read only as the label), `incident_ids`, `matched_rules`, `set_roles`, `mo_name`, `suspicion_score`, `label_confidence`, `lifecycle_stage`, `disposition`, `status_name`, `disposition_category`, `is_false_positive`, `attack_techniques`, `attack_tactics`, `defense_techniques`: never an Event field, never in `extra_fields` |

**Not run on the real files yet.** huggingface.co is blocked from the development container, so the parser is built from the dataset profile (section 4.1) and tested on invented rows. The first `python -m app.ingest.cli precinct6 <slice.jsonl> --profile` on a team machine lists the columns, labels, streams and message types (counts only, no entity or CON-20 value) to confirm it.
