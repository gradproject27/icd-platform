# Ingestion: parser, normalizer, labels and quarantine (C2, Week 2)

Owner: **C2**. How an uploaded file becomes `Event` records (contracts v1) or quarantined records, and how the intake summary is counted. Plan: "ICD Week 2 Detailed Plan", section 5. Decisions: C2 Week 2 D1 to D14 (proposed, team to confirm).

## 1. Where it runs

C1's worker calls one parser per dataset (`docs/api-upload-jobs.md` section 5, accepted by C2 as written):

```python
parse(path: Path, context: IntakeContext) -> Iterator[Event | Quarantined]
```

- One item per record read, in file order. One bad record never raises; `ParseError` only when the whole file cannot be read.
- The parser never writes to the database. The worker stores events in `events` and the rest in `quarantined_records` (C1 migration `0002`), and counts both into `IntakeCounts`.
- Parsers are registered by `dataset_id` in `backend/app/ingest/registry.py`. Week 2: `fixture` (C1) and **`unsw-nb15`** (C2).

| Module (`backend/app/ingest/`) | Job |
|---|---|
| `unsw_nb15.py` | UNSW-NB15 parser and the aggregate-only profile |
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

`contracts/event-types.json` is the list C2 publishes (contracts v1, open question 1). Types: `network_flow`, `http_request`, `dns_query`, `ftp_session`, `ftp_data_transfer`, `smtp_session`, `pop3_session`, `ssh_session`, `tls_session`, `snmp_request`, `irc_session`, `radius_request`, `dhcp_request`, `unknown`. Each source maps one activity column; a value not in the map is `unknown`. C3's fixture names (`network_scan`, `fuzzing`, ...) are placeholders, not part of this list.

## 5. Quarantine reason codes

Every quarantined record keeps `record_ref` (file and line), the reason in plain words and the first 500 characters of the line (NUL bytes replaced).

| Code | When |
|---|---|
| `empty_record` | The line is empty or only spaces |
| `bad_encoding` | The line is not UTF-8, or holds a NUL byte |
| `line_too_long` | The line is longer than 64 KiB (the rest of the line is skipped, the next line is read) |
| `bad_csv` | The CSV reader rejects the line |
| `wrong_column_count` | Not 49 columns |
| `missing_timestamp` | `Stime` is empty |
| `bad_timestamp` | `Stime` is not epoch seconds or is outside 1990 to 2100 |
| `unknown_label` | The label value is not in the label mapping (rule `unknown_value`) |
| `pending_label` | The label value is listed with a pending decision (rule `pending_values`) |
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

labelled + unlabelled + quarantined = records read. The full upload job with PostgreSQL was not timed on the real file; on the synthetic file of the same size it took about 2.8 times the parser time.
