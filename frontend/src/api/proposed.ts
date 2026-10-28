import type { Incident } from "./contracts";

// Proposed for C3; not a shared contract yet. The Incident contract has no entity values
// (only link_keys), but the Week 2 plan's list shows entities. See docs/wireframes.md 4.3.
//
// Proposed endpoints (paths as the API sees them, after /api is stripped):
//   GET /incidents                -> 200 IncidentList
//   GET /incidents/{incident_id}  -> 200 IncidentSummary, or 404 in C1's error shape

/** Proposed for C3; not a shared contract yet. Each list is sorted and has no duplicates. */
export interface IncidentEntities {
  hosts: string[];
  users: string[];
  ips: string[];
}

/** Proposed for C3; not a shared contract yet. */
export interface IncidentSummary {
  incident: Incident;
  entities: IncidentEntities;
}

/** Proposed for C3; not a shared contract yet. */
export interface IncidentList {
  items: IncidentSummary[];
}
