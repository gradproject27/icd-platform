import type { Incident, IncidentStatus, ResponseAction, ScenarioId } from "./contracts";

// Proposed for C3; not a shared contract yet. The Incident contract has no entity values
// (only link_keys), but the Week 2 plan's list shows entities. See docs/wireframes.md 4.3.
//
// Proposed endpoints (paths as the API sees them, after /api is stripped):
//   GET /incidents                -> 200 IncidentList
//   GET /incidents/{incident_id}  -> 200 IncidentSummary, or 404 in C1's error shape
//
// Decision endpoints, proposed for C5 (response-workflow-spec.md sections 8 and 10):
//   GET  /incidents/{incident_id}/decision   -> 200 DecisionRecord, or 404 when none is recorded
//   POST /incidents/{incident_id}/decisions  DecisionRequest -> 201 DecisionRecord;
//        409 when the window expired or a decision already exists, 403 when the user may not decide,
//        422 for an invalid request; every error in C1's error shape

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
  /**
   * Proposed for C5; not a shared contract yet. The scenario the response engine's catalogue
   * lookup recommends on entry to Awaiting Human Decision (spec section 6); null when no scenario
   * matches. Absent while the endpoint does not send it.
   */
  recommended_scenario_id?: ScenarioId | null;
}

/** Proposed for C3; not a shared contract yet. */
export interface IncidentList {
  items: IncidentSummary[];
}

/**
 * Proposed for C5; not a shared contract yet. The three analyst options of spec section 8:
 * approve the recommended scenario, reject it, or select another catalogue scenario.
 */
export type DecisionType = "approve" | "reject" | "select";

/** Proposed for C5; not a shared contract yet. Body of POST /incidents/{incident_id}/decisions. */
export interface DecisionRequest {
  decision: DecisionType;
  /** The recommended scenario for approve, the chosen one for select, null for reject. */
  scenario_id: ScenarioId | null;
  /** The open response window the decision answers, or null when there is none. */
  window_id: string | null;
  /** Optional analyst comment (FR-28); null when empty. */
  comment: string | null;
}

/** Proposed for C5; not a shared contract yet. A recorded decision (FR-28). */
export interface DecisionRecord {
  incident_id: string;
  window_id: string | null;
  decision: DecisionType;
  scenario_id: ScenarioId | null;
  comment: string | null;
  /** User ID of the decision maker. */
  decided_by: string;
  /** UTC, ISO 8601. */
  decided_at: string;
  /** The incident's lifecycle state after the decision. */
  incident_status: IncidentStatus;
  /**
   * Proposed for C5; not a shared contract yet. The simulated action of an approve or select, as
   * the ResponseAction contract; null for reject.
   */
  action: ResponseAction | null;
}
