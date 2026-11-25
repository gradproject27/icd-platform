/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Simulated response catalogue v0 (OD-20). Anything else is rejected (FR-44).
 *
 * This interface was referenced by `ScenarioCatalogue`'s JSON-Schema
 * via the `definition` "ScenarioId".
 */
export type ScenarioId = "S1" | "S2" | "S3" | "S4";

/**
 * GET /scenarios: the simulated catalogue v0 with display metadata. Every one is simulated.
 */
export interface ScenarioCatalogue {
  /**
   * response.toml config_version.
   */
  config_version: string;
  items: ScenarioItem[];
  /**
   * scenario_meta.toml config_version.
   */
  meta_version: string;
}
/**
 * One simulated scenario of the catalogue, with its display metadata (P6).
 *
 * This interface was referenced by `ScenarioCatalogue`'s JSON-Schema
 * via the `definition` "ScenarioItem".
 */
export interface ScenarioItem {
  /**
   * May the system select it at the deadline (response.toml).
   */
  automatic: boolean;
  /**
   * From scenario_meta.toml.
   */
  impact: "low" | "medium" | "high";
  /**
   * Targets it needs.
   */
  needs: ("source_ip" | "account")[];
  reversible: boolean;
  /**
   * How the simulated effect ends, in plain words.
   */
  revert: string;
  scenario_id: ScenarioId;
  /**
   * From response.toml.
   */
  title: string;
}
