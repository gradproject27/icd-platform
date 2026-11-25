/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * GET /incidents/{incident_id}/key-facts: computed by code, never by the model.
 *
 * Only flagged events count (OD-02). Internal and external addresses follow response.toml
 * [network] (decision D3). Each list is ordered by first appearance, then value, and holds at
 * most 20 items; `truncated` says a list was cut.
 */
export interface IncidentKeyFacts {
  /**
   * User names on flagged events.
   */
  accounts: KeyFactItem[];
  /**
   * Dataset attack types (labels).
   */
  attack_types: KeyFactItem[];
  context_event_count: number;
  destination_ports: KeyFactItem[];
  /**
   * Source or destination IPs, external.
   */
  external_ips: KeyFactItem[];
  /**
   * The earliest flagged event.
   */
  first_flagged_event_id: string;
  flagged_event_count: number;
  hosts: KeyFactItem[];
  incident_id: string;
  /**
   * Source or destination IPs, internal.
   */
  internal_ips: KeyFactItem[];
  /**
   * Time of the latest flagged event, UTC.
   */
  last_flagged_at: string;
  /**
   * The latest flagged event.
   */
  last_flagged_event_id: string;
  /**
   * response.toml config_version that split internal from external addresses.
   */
  network_config_version: string;
  /**
   * Source IP of the earliest flagged event when it is external; else null.
   */
  origin_ip: string | null;
  /**
   * Count and order markers (P5), earliest first. Markers only: they never flag an event, infer a label or change a score.
   */
  patterns: KeyFactPattern[];
  /**
   * patterns.toml config_version of the count and order markers.
   */
  patterns_config_version: string;
  /**
   * Time of the earliest flagged event, UTC.
   */
  started_at: string;
  /**
   * Host of the earliest flagged event, else its internal destination IP.
   */
  started_on: string | null;
  /**
   * MITRE ATT&CK tactics ('TA0043 Reconnaissance') of those attack types, from the reviewed table tactics.toml; never chosen by the model. ATT&CK (c) MITRE.
   */
  tactics: KeyFactItem[];
  /**
   * tactics.toml config_version that mapped attack types to ATT&CK tactics.
   */
  tactics_config_version: string;
  /**
   * True when a list held more than 20 values and was cut.
   */
  truncated: boolean;
}
/**
 * One distinct value among the incident's flagged events, with the events it comes from.
 *
 * This interface was referenced by `IncidentKeyFacts`'s JSON-Schema
 * via the `definition` "KeyFactItem".
 */
export interface KeyFactItem {
  /**
   * Flagged events that carry the value.
   */
  event_count: number;
  /**
   * The first of those events (at most 10), oldest first.
   *
   * @minItems 1
   * @maxItems 10
   */
  event_ids:
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string, string, string];
  /**
   * Time of the first of those events, UTC.
   */
  first_seen: string;
  /**
   * The value: an attack type, host, IP, port or user.
   */
  value: string;
}
/**
 * A count or order marker over the flagged events (P5, patterns.toml). Flags nothing.
 *
 * This interface was referenced by `IncidentKeyFacts`'s JSON-Schema
 * via the `definition` "KeyFactPattern".
 */
export interface KeyFactPattern {
  /**
   * The flagged events, oldest first.
   *
   * @minItems 2
   */
  event_ids: [string, string, ...string[]];
  first_seen: string;
  /**
   * What the events share: source and attack type, or host.
   */
  key: string;
  pattern_id: string;
  title: string;
}
