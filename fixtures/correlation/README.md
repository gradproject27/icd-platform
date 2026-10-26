# Correlation fixtures (C3, Week 2)

A small hand-built event set for the correlation engine v0 (T2-08), the risk score (T2-09) and the Friday demo. The expected incidents were written **before** any engine code.

| File | Content |
|---|---|
| `events.json` | 37 events in the `Event` contract (v1.0): 18 flagged, 17 unflagged, 2 unlabelled. All on 15 Jan 2026, UTC |
| `expected-incidents.json` | The 8 expected incidents (flagged events, context events, `link_keys`, times, incident type, hosts, attack types, privileged) and the 14 events that stay outside any incident, each with a reason |

`backend/tests/test_correlation_fixtures.py` validates every event against the contract. It also recomputes the expected incidents with a brute-force all-pairs reference, so a mistake in the hand-written answers fails CI. The real engine (Step 2) will be tested against the same file.

**Placeholders only.** Hosts (`web-01`, `ws-41`), users (`user-b`, `svc-db`) and IPs (10.0.0.0/8 and the documentation ranges 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) are invented. No dataset values (NFR-S-07; the repository is public). Attack types use the UNSW-NB15 category names (provisional, decision D2). The label raw values are `1` (flagged) and `0` (unflagged), as in the UNSW-NB15 `label` column.

**Rules used.** `docs/correlation-and-risk-design.md`, with every proposed default of its section 15: 15-minute gap window with an inclusive boundary (Q1), keys `host`, unordered `ip_pair` (Q2) and `user`, event type not a key (Q4), context never merges groups (Q5), nearest-in-time context with ties to the earliest group (Q6), and incident of one event (Q7).

## Cases and expected incidents

### A. Multi-step attack (1 incident, 8 flagged + 3 context)

| Time | Event | Label | Attack type | Host | User | Why it joins |
|---|---|---|---|---|---|---|
| 08:40 | fx-001 | unflagged | | web-01 | | **Not attached**: 20 min before fx-002 |
| 09:00 | fx-002 | flagged | Reconnaissance | web-01 | | Starts incident A |
| 09:02 | fx-003 | unflagged | | web-01 | | Context (host, 2 min) |
| 09:04 | fx-004 | flagged | Reconnaissance | web-01 | | host + ip_pair with fx-002 |
| 09:10 | fx-007 | flagged | Exploits | web-01 | www-data | host + ip_pair with fx-004 |
| 09:18 | fx-008 | flagged | Backdoors | web-01 | www-data | host, ip_pair (reverse direction) and user |
| 09:30 | fx-009 | flagged | Exploits | db-01 | www-data | user only (12 min): the attack moves to db-01 |
| 09:42 | fx-010 | flagged | Exploits | db-01 | svc-db (privileged) | host + ip_pair with fx-009 |
| 09:45 | fx-011 | unflagged | | db-01 | svc-db | Context (host + user, 3 min) |
| 09:55 | fx-012 | flagged | Backdoors | db-01 | svc-db | host + user (13 min) |
| 10:08 | fx-013 | flagged | Backdoors | file-01 | svc-db | user only (13 min): the attack moves to file-01 |
| 10:10 | fx-014 | **unlabelled** | | file-01 | svc-db | Context (host + user): unlabelled is treated like unflagged |

The chain runs 68 minutes, although no step is more than 15 minutes from the previous one (gap window). It has 3 hosts and 3 attack types, and a privileged account is involved. Incident type: Exploits and Backdoors both appear 3 times, and the tie goes to the higher severity, so the type is **Backdoors**.

### B. Benign group (no incident)
fx-015 to fx-020: six unflagged events of `user-b` on `ws-30`, 11:00 to 11:30. Context alone never creates an incident.

### C. Ambiguous case (2 incidents that must stay separate)

| Time | Event | Label | Host | User | Result |
|---|---|---|---|---|---|
| 13:00 | fx-021 | flagged, Fuzzers | ws-41 | | Starts C1 |
| 13:05 | fx-022 | flagged, Fuzzers | ws-41 | | C1 |
| 13:14:30 | fx-023 | unflagged | ws-41 | admin-shared | 9.5 min from C1 (host) **and** 9.5 min from C2 (user): tie, so it goes to the earliest group, **C1** |
| 13:16 | fx-024 | unflagged | ws-41 | admin-shared | 11 min from C1, 8 min from C2: **C2** |
| 13:24 | fx-025 | flagged, DoS | ws-42 | admin-shared | Starts C2 |
| 13:30 | fx-026 | flagged, DoS | ws-42 | admin-shared | C2 |
| 13:40 | fx-027 | unflagged | ws-41 | | **Not attached**: 35 min after C1 |

fx-023 and fx-024 share a key with both groups, but **context never merges groups**, so C1 and C2 stay two incidents. `admin-shared` has `privileged_user = false`, so C2's privileged value is false. All other incidents except A are null (not in data).

### D. Window boundary (3 incidents)
- `ws-50`: fx-028 at 15:00:00 and fx-029 at 15:15:00, **exactly** 15 min apart. They are linked (inclusive boundary), so this is one incident **D1**. Type: Reconnaissance and Generic tie 1–1, and the higher severity wins, so the type is **Generic**.
- `ws-51`: fx-030 at 15:00:00 and fx-031 at 15:15:01, one second too far apart. These are two incidents of one event, **D2a** and **D2b**.

### E. Isolated flagged event without an attack type (1 incident)
fx-032 on `ws-60` at 17:00 gives an incident of one event with `incident_type = null`. fx-033 (17:30, same host) is 30 min later, so it is not attached.

### F. Events with no key (1 incident)
fx-005 is flagged and has no host, IP or user. It can never link, so it becomes an incident of one event **F**, even though it sits in the middle of attack A's time range. fx-006 is unflagged and has no key, so it stays outside.

### Noise
fx-034 to fx-037: unrelated unflagged and unlabelled events. None is attached.

## Summary

| Incident | Start | Flagged | Context | Hosts | Type | Privileged |
|---|---|---|---|---|---|---|
| A | fx-002 | 8 | 3 | db-01, file-01, web-01 | Backdoors | true |
| F | fx-005 | 1 | 0 | (none) | Generic | null |
| C1 | fx-021 | 2 | 1 | ws-41 | Fuzzers | null |
| C2 | fx-025 | 2 | 1 | ws-42 | DoS | false |
| D1 | fx-028 | 2 | 0 | ws-50 | Generic | null |
| D2a | fx-030 | 1 | 0 | ws-51 | Reconnaissance | null |
| D2b | fx-031 | 1 | 0 | ws-51 | Reconnaissance | null |
| E | fx-032 | 1 | 0 | ws-60 | null | null |

18 flagged events become 8 incidents (alert compression 2.25). 14 events stay outside any incident.

## If the team changes a default

| Decision | What changes in the expected file |
|---|---|
| Q1: boundary exclusive (`< 15 min`) | D1 splits into two incidents |
| Q5: context may merge groups | C1 and C2 become one incident |
| Q6: a different tie rule | fx-023 moves from C1 to C2 |
| Q7: no incident of one event | F, D2a, D2b and E disappear |
| D2: a different severity order | Only the type of A (Backdoors vs Exploits) and D1 (Generic vs Reconnaissance) can change |

Risk scores are **not** in this file yet. They are added in Step 3, once the risk method is chosen.
