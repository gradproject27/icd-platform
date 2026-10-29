/* GENERATED from contracts/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Status of the AI analysis. Analysis failed is a status, not a lifecycle state (OD-09).
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "AnalysisStatus".
 */
export type AnalysisStatus = "not_started" | "in_progress" | "succeeded" | "failed";
/**
 * The entity key that linked an event to the incident (NFR-SF-05).
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "LinkKey".
 */
export type LinkKey = "host" | "ip_pair" | "user";
/**
 * Why an event belongs to an incident. Context events are never treated as malicious.
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "EventRole".
 */
export type EventRole = "flagged" | "context";
/**
 * Something the score had to assume because the data does not say (contracts 1.1).
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "RiskFlag".
 */
export type RiskFlag = "asset_unknown" | "outcome_unknown" | "severity_default";
/**
 * Risk level derived from the score by C3's configurable thresholds (FR-20).
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "RiskLevel".
 */
export type RiskLevel = "low" | "medium" | "high";
/**
 * Lifecycle state (FR-31, TD-11). new replaces the former name Detected.
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "IncidentStatus".
 */
export type IncidentStatus =
  "new" | "under_analysis" | "awaiting_human_decision" | "response_in_progress" | "escalated" | "resolved" | "closed";

/**
 * A group of related events (FR-07, FR-08, FR-11, FR-18 to FR-20, FR-31, FR-42).
 */
export interface Incident {
  /**
   * Number of analysis attempts.
   */
  analysis_attempts?: number;
  analysis_status?: AnalysisStatus;
  /**
   * Confidence of the latest valid analysis (OD-16); set exactly when analysis succeeded (FR-42).
   */
  confidence?: number | null;
  /**
   * When the incident was created, UTC.
   */
  created_at: string;
  /**
   * Linked events (FR-08); event IDs are unique.
   *
   * @minItems 1
   */
  events: [IncidentEventLink, ...IncidentEventLink[]];
  /**
   * Timestamp of the earliest event, UTC.
   */
  first_event_at: string;
  /**
   * Unique incident ID.
   */
  incident_id: string;
  /**
   * C3 classification, read by C5's scenario lookup (OD-20); null = not classified yet.
   */
  incident_type?: string | null;
  /**
   * Timestamp of the latest event, UTC; not before first_event_at.
   */
  last_event_at: string;
  /**
   * ID of the latest valid AnalysisReport; required when analysis succeeded.
   */
  latest_report_id?: string | null;
  /**
   * Deterministic risk assessment; null = not scored yet.
   */
  risk?: RiskAssessment | null;
  /**
   * Contract version.
   */
  schema_version?: "1.0";
  status?: IncidentStatus;
  /**
   * Last change, UTC; not before created_at.
   */
  updated_at: string;
}
/**
 * Link from an incident to one event (FR-08).
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "IncidentEventLink".
 */
export interface IncidentEventLink {
  /**
   * ID of the linked Event.
   */
  event_id: string;
  /**
   * Keys that linked the event. Empty only for the event that started the incident.
   */
  link_keys: LinkKey[];
  /**
   * When the event was linked, UTC.
   */
  linked_at: string;
  role: EventRole;
}
/**
 * Deterministic risk score computed by C3 code, never by the LLM (OD-04, OD-05, FR-18).
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "RiskAssessment".
 */
export interface RiskAssessment {
  /**
   * When the score was computed, UTC.
   */
  computed_at: string;
  /**
   * Version of the weights and thresholds file used.
   */
  config_version: string;
  /**
   * Per-factor breakdown (FR-19).
   *
   * @minItems 1
   */
  factors: [RiskFactor, ...RiskFactor[]];
  /**
   * Assumptions the score made (contracts 1.1).
   */
  flags?: RiskFlag[];
  /**
   * Asset impact I, 0 to 1 (contracts 1.1).
   */
  impact?: number | null;
  level: RiskLevel;
  /**
   * Combined evidence strength L, 0 to 1 (contracts 1.1).
   */
  likelihood?: number | null;
  /**
   * Risk score as a percentage (FR-18).
   */
  score: number;
  /**
   * The strongest evidence groups, strongest first (contracts 1.1).
   *
   * @maxItems 3
   */
  top_contributors?:
    [] | [RiskContributor] | [RiskContributor, RiskContributor] | [RiskContributor, RiskContributor, RiskContributor];
}
/**
 * One factor of the deterministic risk score.
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "RiskFactor".
 */
export interface RiskFactor {
  /**
   * Points this factor adds to the score.
   */
  contribution: number;
  /**
   * Factor name from the risk configuration.
   */
  name: string;
  /**
   * Plain-language reason for the factor's value (contracts 1.1, additive).
   */
  reason?: string | null;
  /**
   * Normalized factor value, 0 to 1.
   */
  value: number;
  /**
   * Weight of the factor in the configuration.
   */
  weight: number;
}
/**
 * One evidence group behind the score: its strongest event (contracts 1.1).
 *
 * This interface was referenced by `Incident`'s JSON-Schema
 * via the `definition` "RiskContributor".
 */
export interface RiskContributor {
  /**
   * Source-side entity of the group, or none.
   */
  entity: string;
  /**
   * ID of the group's strongest flagged event.
   */
  event_id: string;
  /**
   * Plain-language reason for the strength.
   */
  reason: string;
  /**
   * Strength of the group's strongest event, 0 to 1.
   */
  strength: number;
  /**
   * Attack type of the group; unknown when missing.
   */
  technique: string;
}
