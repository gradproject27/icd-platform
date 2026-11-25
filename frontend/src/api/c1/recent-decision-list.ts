/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * The four roles (D7.1).
 *
 * This interface was referenced by `RecentDecisionList`'s JSON-Schema
 * via the `definition` "UserRole".
 */
export type UserRole = "soc_analyst" | "soc_manager" | "security_engineer" | "system_administrator";
/**
 * Simulated response catalogue v0 (OD-20). Anything else is rejected (FR-44).
 *
 * This interface was referenced by `RecentDecisionList`'s JSON-Schema
 * via the `definition` "ScenarioId".
 */
export type ScenarioId = "S1" | "S2" | "S3" | "S4";

/**
 * GET /decisions/recent?hours=: decisions of the last hours (default 72), newest first.
 */
export interface RecentDecisionList {
  hours: number;
  /**
   * At most 200.
   */
  items: RecentDecision[];
  since: string;
  /**
   * The server clock when it answered.
   */
  until: string;
}
/**
 * An analyst decision (decision.recorded) or a system selection at the deadline
 * (scenario.selected), from the audit trail.
 *
 * This interface was referenced by `RecentDecisionList`'s JSON-Schema
 * via the `definition` "RecentDecision".
 */
export interface RecentDecision {
  actor: string;
  actor_role: UserRole | null;
  by: "analyst" | "system";
  comment: string | null;
  decision: "approve" | "reject" | "select" | "no_action" | "system_selection";
  incident_id: string;
  occurred_at: string;
  /**
   * The audit record.
   */
  record_id: string;
  scenario_id: ScenarioId | null;
}
