/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Risk level derived from the score by C3's configurable thresholds (FR-20).
 *
 * This interface was referenced by `EntityRiskList`'s JSON-Schema
 * via the `definition` "RiskLevel".
 */
export type RiskLevel = "low" | "medium" | "high";

/**
 * GET /entity-risk: the entity roll-up (P3). Read-only: never changes an incident score.
 */
export interface EntityRiskList {
  /**
   * entity_risk.toml config_version.
   */
  config_version: string;
  /**
   * Highest score first, then entity.
   */
  items: EntityRiskItem[];
  score_threshold: number;
  /**
   * tactics.toml config_version.
   */
  tactics_config_version: string;
  tactics_threshold: number;
  /**
   * Latest last event of the incidents read.
   */
  window_end: string | null;
  /**
   * Null when no scored incident is read.
   */
  window_start: string | null;
}
/**
 * One source-side entity: source IP, else user, else host of its flagged events.
 *
 * This interface was referenced by `EntityRiskList`'s JSON-Schema
 * via the `definition` "EntityRiskItem".
 */
export interface EntityRiskItem {
  entity: string;
  /**
   * Thresholds reached; nothing acts on them.
   */
  flags: ("score_threshold" | "tactic_threshold")[];
  incident_count: number;
  /**
   * Highest score first.
   */
  incidents: EntityRiskIncident[];
  level: RiskLevel;
  /**
   * Rank-weighted roll-up of its incident scores.
   */
  score: number;
  /**
   * Distinct ATT&CK tactic IDs, sorted.
   */
  tactics: string[];
}
/**
 * This interface was referenced by `EntityRiskList`'s JSON-Schema
 * via the `definition` "EntityRiskIncident".
 */
export interface EntityRiskIncident {
  incident_id: string;
  /**
   * The incident's stored risk score (C3).
   */
  score: number;
}
