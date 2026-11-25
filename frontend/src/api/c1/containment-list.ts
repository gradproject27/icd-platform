/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * GET /incidents/{incident_id}/containments: blocks it started or extended, oldest first.
 */
export interface ContainmentList {
  items: SimulatedContainment[];
}
/**
 * A simulated IP block that ends on its own (P2, containment.toml). Nothing real is blocked.
 *
 * This interface was referenced by `ContainmentList`'s JSON-Schema
 * via the `definition` "SimulatedContainment".
 */
export interface SimulatedContainment {
  /**
   * The action that started the block.
   */
  action_id: string;
  /**
   * containment.toml config_version used.
   */
  config_version: string;
  containment_id: string;
  /**
   * Planned end; the worker reverts the block then.
   */
  ends_at: string;
  /**
   * How often the same IP was blocked again while blocked.
   */
  extended: number;
  /**
   * The incident whose action started the block.
   */
  incident_id: string;
  /**
   * Only S2's simulated IP block is timed.
   */
  kind: "block_ip";
  /**
   * The action that set the current end.
   */
  last_action_id: string;
  /**
   * The incident whose action set the current end.
   */
  last_incident_id: string;
  /**
   * 1 for a first block; n for the n-th repeat in a row.
   */
  offence: number;
  /**
   * When the block ended; null while active.
   */
  reverted_at: string | null;
  /**
   * Always true: nothing real is blocked.
   */
  simulated: true;
  started_at: string;
  status: "active" | "reverted";
  /**
   * The blocked (simulated) source IP.
   */
  target: string;
}
