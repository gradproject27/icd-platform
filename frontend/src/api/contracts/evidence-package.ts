/* GENERATED from contracts/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Dataset label of an event. A missing label is unlabelled, never inferred (OD-21).
 *
 * This interface was referenced by `EvidencePackage`'s JSON-Schema
 * via the `definition` "LabelStatus".
 */
export type LabelStatus = "flagged" | "unflagged" | "unlabelled";
/**
 * Why an event belongs to an incident. Context events are never treated as malicious.
 *
 * This interface was referenced by `EvidencePackage`'s JSON-Schema
 * via the `definition` "EventRole".
 */
export type EventRole = "flagged" | "context";
/**
 * Risk level derived from the score by C3's configurable thresholds (FR-20).
 *
 * This interface was referenced by `EvidencePackage`'s JSON-Schema
 * via the `definition` "RiskLevel".
 */
export type RiskLevel = "low" | "medium" | "high";

/**
 * What the AI receives for one incident (OD-03, NFR-S-07, FR-13).
 */
export interface EvidencePackage {
  /**
   * When the package was built, UTC.
   */
  created_at: string;
  /**
   * Up to 50 events: all flagged events first (up to the cap), then sampled context events (OD-03). Event IDs are unique.
   *
   * @maxItems 50
   */
  events: EvidenceEvent[];
  incident: IncidentContext;
  /**
   * ID of the incident the package describes.
   */
  incident_id: string;
  /**
   * True when host, user and IP values are pseudonymised as consistent tokens within the package, for example host-01 (NFR-S-07).
   */
  masked?: boolean;
  /**
   * Unique package ID.
   */
  package_id: string;
  /**
   * Contract version.
   */
  schema_version?: "1.0";
  /**
   * Events in the incident, before the cap.
   */
  total_event_count: number;
  /**
   * True exactly when events were left out by the cap.
   */
  truncated: boolean;
}
/**
 * The citable view of one Event. Entity values may be masked tokens (NFR-S-07).
 *
 * This interface was referenced by `EvidencePackage`'s JSON-Schema
 * via the `definition` "EvidenceEvent".
 */
export interface EvidenceEvent {
  /**
   * Dataset attack type; null if absent.
   */
  attack_type?: string | null;
  /**
   * Destination IP or masked token; null if absent.
   */
  dst_ip?: string | null;
  /**
   * ID of the Event; the AI cites this ID.
   */
  event_id: string;
  /**
   * Normalized event type.
   */
  event_type: string;
  /**
   * Host or masked token; null if absent.
   */
  host?: string | null;
  label_status: LabelStatus;
  role: EventRole;
  /**
   * Provenance source, for example the file name.
   */
  source: string;
  /**
   * Source IP or masked token; null if absent.
   */
  src_ip?: string | null;
  /**
   * Short description of the event.
   */
  summary: string;
  /**
   * Event time, UTC.
   */
  timestamp: string;
  /**
   * Account or masked token; null if absent.
   */
  user?: string | null;
}
/**
 * Incident metadata given to the AI (OD-03).
 *
 * This interface was referenced by `EvidencePackage`'s JSON-Schema
 * via the `definition` "IncidentContext".
 */
export interface IncidentContext {
  /**
   * Context events in the incident.
   */
  context_event_count: number;
  /**
   * Timestamp of the earliest event, UTC.
   */
  first_event_at: string;
  /**
   * Flagged events in the incident.
   */
  flagged_event_count: number;
  /**
   * Distinct hosts in the incident.
   */
  host_count: number;
  /**
   * Incident type; null = not classified yet.
   */
  incident_type?: string | null;
  /**
   * Timestamp of the latest event, UTC.
   */
  last_event_at: string;
  /**
   * Risk level; null = not scored.
   */
  risk_level?: RiskLevel | null;
  /**
   * Deterministic risk score; null = not scored.
   */
  risk_score?: number | null;
}
