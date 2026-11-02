# Evidence package builder and masking (C2, Week 3)

| | |
|---|---|
| **Owner** | C2, Datasets & Evidence |
| **Tasks** | T3-06 evidence package builder (workflow step 4); T3-07 masking, first part (workflow step 10) |
| **Decisions** | Team plan W3-D4, W3-D5; C2-D1 to C2-D7 (approved by C2, 2 Nov 2026) |
| **Code** | `backend/app/evidence/` (`builder.py`, `masking.py`, `cli.py`); tests in `backend/tests/evidence/` |

## 1. What it does

`build_package(incident, events, created_at)` turns one C3 `Incident` and its `Event`s into the `EvidencePackage` the AI receives (contract in `backend/app/contracts/evidence.py`), and returns the masking map with it. It is a pure function: no database, no clock. When C1's incidents table exists, a small loader reads the incident and its events and calls it.

```
Incident (C3) + Events (C2 parser) ──► select ≤ 50 events ──► EvidenceEvent view ──► mask ──► EvidencePackage (masked=true) ──► C1 analysis job ──► AI1 prompt
                                                                                        └──► masking map (stays on the app host)
```

## 2. Which events go in (W3-D4, C2-D2)

1. All flagged events, in time order (ties by event ID), up to 50.
2. The free places go to context events (unflagged or unlabelled), nearest in time to a flagged event in the package; ties by time, then event ID. Never random, so one incident always gives the same package.
3. `total_event_count` = all events of the incident; `truncated` = true exactly when some were left out.
4. `incident` holds the type, risk score and level, first and last event time, flagged and context counts over the **whole** incident, and the number of distinct real hosts (0 for UNSW-NB15, which has no host column).

Refused: a linked event that was not given (`MissingEvents`), and an incident role that does not match the event's label.

`package_id` = `pkg-<incident_id>-<first 12 hex of SHA-256 of the incident context and masked events>` (C2-D3). `created_at` is not part of it, so the same evidence keeps the same ID; this also suits AI1's report cache key (W3-D8).

## 3. Masking (W3-D5, C2-D4, C2-D5)

| Field | Token |
|---|---|
| `host` | `host-01`, `host-02`, … |
| `src_ip`, `dst_ip` (one numbering) | `ip-01`, `ip-02`, … |
| `user` | `user-01`, … |

- Numbered per incident in first-seen order, in package order. One value always gets the same token inside an incident, so the AI still sees that two events share a machine. Tokens do not carry across incidents.
- The style is the one the contract, AI1's prompt and AI1's grounding check (`MASKED_TOKEN`) already use, so the grounding check can tell a token the model invented from one in the package.
- A real value that slipped into a `summary` or `source` is replaced too (whole values only: `10.0.0.1` is not replaced inside `10.0.0.12`).
- Before returning, the builder serializes the package and checks that no real value is left (`find_leaks`); if one is, it raises `MaskingLeak` instead of returning the package.
- Every package is masked (`masked=true`); there is no unmasked mode (C2-D4). C1's handoff refuses `masked=false`.

## 4. The map and the report (C2-D6, C2-D7)

`MaskingMap` holds `token → (kind, real value)` for one incident. It never goes to the HPC. The report is stored **masked**, as the model wrote it, so AI1's grounding checks compare it with the package it was given. Only the API un-masks it for the analyst (`MaskingMap.unmask(text)`). Storing the map (migration 0006, `masking_maps`) and the un-masking endpoint come in the next C2 PR (T3-07, due Fri 6).

## 5. Try it

```
cd backend
python -m app.evidence.cli ../fixtures/correlation/events.json
python -m app.evidence.cli ../fixtures/correlation/events.json --incident inc-852bbfaea14e44fb
```

The first prints one line per incident (events in the package / in the incident, truncated, number of tokens, package ID); the second prints one whole masked package. The map is never printed.
