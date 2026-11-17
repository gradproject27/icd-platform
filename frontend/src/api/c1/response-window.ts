/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Simulated response catalogue v0 (OD-20). Anything else is rejected (FR-44).
 *
 * This interface was referenced by `ResponseWindow`'s JSON-Schema
 * via the `definition` "ScenarioId".
 */
export type ScenarioId = "S1" | "S2" | "S3" | "S4";
/**
 * This interface was referenced by `ResponseWindow`'s JSON-Schema
 * via the `definition` "ResponseWindowStatus".
 */
export type ResponseWindowStatus = "open" | "decided" | "expired";

/**
 * GET /response-windows/{incident_id}: the latest window, for the countdown (spec 7).
 */
export interface ResponseWindow {
  deadline_at: string;
  incident_id: string;
  recommended_scenario_id: ScenarioId | null;
  /**
   * The database clock when the server answered.
   */
  server_time: string;
  started_at: string;
  status: ResponseWindowStatus;
  window_id: string;
}
