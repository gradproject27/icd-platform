# Incident storage (Week 3)

| | |
|---|---|
| Owner | C1 (Platform & Integration) |
| Status | **Built:** tables, `store_incidents()`, `correlate_upload()`, and the `correlating` stage at the end of every ingest job (decision D3) |
| Code | `backend/app/incidents/` (`models.py`, `store.py`), migration `0005`; tests in `backend/tests/incidents/` |

C3's correlation (`app.correlation.engine.correlate`) returns `Incident` contracts. Until now nothing kept them. This adds a fixed place in the database for incidents and their links to the stored events. C2's evidence builder and C5's response engine can then read an incident by its ID.

## Tables (migration 0005)

| Table | One row per | Columns |
|---|---|---|
| `incidents` | Incident | `incident_id` (key), `upload_id` (the upload whose events it links), `status`, `incident_type`, `risk_score`, `risk_level`, `first_event_at`, `last_event_at`, `created_at`, `updated_at`, `correlation_config_version`, `data` (the full Incident JSON, as C3 built it) |
| `incident_events` | Link from an incident to one event | `incident_id`, `event_id` (key together), `upload_id`, `role` (`flagged` or `context`), `link_keys`, `linked_at` |

- `data` is the source of truth. The other columns are copies for querying and sorting.
- `incident_events` points at the stored event through `(upload_id, event_id)`, so the database refuses a link to an event that is not stored.
- Deleting an incident deletes its links.
- When an upload's rows are cleared (an ingest retry, or a job failed with `worker_lost`), its incidents are deleted with its events.

## For C3: how to store incidents

```python
from app.incidents.store import store_incidents

result = correlate(events, config, now)
store_incidents(engine, upload_id, result.incidents, result.config_version)
```

Or in one call, from the events already stored for an upload:

```python
from app.incidents.store import correlate_upload

incidents = correlate_upload(engine, upload_id, now)
```

How `store_incidents` behaves:
- **All or nothing.** It writes every incident of the call and all its links in one transaction, or nothing.
- **Same input, same rows.** Storing an incident that is already stored replaces it and its links. Incident IDs are deterministic, so running the correlation again on the same upload does not duplicate anything.
- **Refusals, which write nothing:**
  - `MissingEvents`: a linked event is not stored for this upload.
  - `IncidentConflict`: the incident ID is already stored for another upload. This happens when the same events are uploaded twice; see D4.

To read incidents back, use `load_incident(engine, incident_id)` and `load_incidents(engine, upload_id)`. Both return `Incident` contracts.

## Open decisions

| # | Question | Proposed | Who |
|---|---|---|---|
| D1 | Owner of incident storage | C1 owns the tables and `store_incidents`; C3 owns what goes in them | Team |
| D2 | Migration order | Numbered in merge order (W3-D2): `0005` is this one. Any later migration takes the next number when it merges | Team |
| D3 | When the correlation runs | **Decided 15 Nov:** a `correlating` stage at the end of the ingest job. After the events are stored, the worker calls `correlate_upload`, and the job is `done` only when the incidents are stored too. If it fails, the job fails with `correlation_failed` and nothing from the upload is kept | C3, C1 |
| D4 | Same events in two uploads | `correlate_upload` scopes each incident ID to its upload (C3's `incident_id_for` over `upload_id/starting event`), so the same events in two uploads give two sets of incidents, still deterministic per upload. `store_incidents` called directly with an ID already stored for another upload refuses with `IncidentConflict`. The duplicate-upload guard (same SHA-256, Week 4) should stop most duplicates earlier. C3 may prefer to add the scope inside `correlate()` | C2, C3 |
| D5 | Incident state | The `status` column is the contract's value as stored. C5 keeps the live state in `incident_lifecycle` (C5 decision D1) until C5 moves it here | C5 |
