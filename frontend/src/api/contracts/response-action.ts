/* GENERATED from contracts/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Simulated response catalogue v0 (OD-20). Anything else is rejected (FR-44).
 *
 * This interface was referenced by `ResponseAction`'s JSON-Schema
 * via the `definition` "ScenarioId".
 */
export type ScenarioId = "S1" | "S2" | "S3" | "S4";
/**
 * State of the action (response spec section 12, written there with hyphens).
 *
 * This interface was referenced by `ResponseAction`'s JSON-Schema
 * via the `definition` "ActionState".
 */
export type ActionState = "proposed" | "approved" | "simulated_succeeded" | "simulated_failed";
/**
 * What caused the action to be decided.
 *
 * This interface was referenced by `ResponseAction`'s JSON-Schema
 * via the `definition` "ActionTrigger".
 */
export type ActionTrigger = "analyst_decision" | "window_expiry";

/**
 * A proposed or simulated response action (FR-23, FR-27, FR-28, FR-44, FR-45, OD-20).
 */
export interface ResponseAction {
  /**
   * Unique action ID.
   */
  action_id: string;
  /**
   * Optional analyst comment (FR-28).
   */
  comment?: string | null;
  /**
   * When it was decided, UTC; null while proposed.
   */
  decided_at?: string | null;
  /**
   * User ID, or system; null while proposed.
   */
  decided_by?: string | null;
  /**
   * When it was simulated, UTC; null until simulated.
   */
  executed_at?: string | null;
  /**
   * Why the simulation failed; only for simulated_failed.
   */
  failure_reason?: string | null;
  /**
   * ID of the incident.
   */
  incident_id: string;
  /**
   * Scenario parameters, for example block_ip.
   */
  parameters?: {
    [k: string]: string | number | boolean | null | undefined;
  };
  /**
   * When the action was proposed, UTC.
   */
  proposed_at: string;
  scenario_id: ScenarioId;
  /**
   * Contract version.
   */
  schema_version?: "1.0";
  /**
   * Always true. No real system is touched (NFR-SF-01).
   */
  simulated?: true;
  state: ActionState;
  target: ActionTarget;
  /**
   * Analyst decision or window expiry; null while proposed, because nobody knows yet which will decide.
   */
  trigger?: ActionTrigger | null;
  /**
   * Response window the action came from, if any.
   */
  window_id?: string | null;
}
/**
 * Target of the simulated action (response spec section 9).
 *
 * This interface was referenced by `ResponseAction`'s JSON-Schema
 * via the `definition` "ActionTarget".
 */
export interface ActionTarget {
  /**
   * Account to disable; S3.
   */
  account?: string | null;
  /**
   * Target host; every scenario.
   */
  host?: string | null;
  /**
   * Source IP to block; S2.
   */
  ip?: string | null;
}
