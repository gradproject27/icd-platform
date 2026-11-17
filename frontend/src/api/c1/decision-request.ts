/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * This interface was referenced by `DecisionRequest`'s JSON-Schema
 * via the `definition` "DecisionType".
 */
export type DecisionType = "approve" | "reject" | "select" | "no_action";
/**
 * Simulated response catalogue v0 (OD-20). Anything else is rejected (FR-44).
 *
 * This interface was referenced by `DecisionRequest`'s JSON-Schema
 * via the `definition` "ScenarioId".
 */
export type ScenarioId = "S1" | "S2" | "S3" | "S4";

/**
 * POST /incidents/{incident_id}/decisions.
 */
export interface DecisionRequest {
  comment?: string | null;
  decision: DecisionType;
  scenario_id?: ScenarioId | null;
  window_id?: string | null;
}
