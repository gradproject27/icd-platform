/* GENERATED from contracts/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Dataset label of an event. A missing label is unlabelled, never inferred (OD-21).
 *
 * This interface was referenced by `Event`'s JSON-Schema
 * via the `definition` "LabelStatus".
 */
export type LabelStatus = "flagged" | "unflagged" | "unlabelled";

/**
 * One normalized security event (FR-02, FR-04, FR-05, FR-40, FR-41, OD-21, TD-12).
 */
export interface Event {
  /**
   * Destination IP; null if absent.
   */
  dst_ip?: string | null;
  /**
   * Destination port; null if absent.
   */
  dst_port?: number | null;
  /**
   * Unique and stable across re-ingestion of the same record. A record without one is rejected by C2 (FR-03).
   */
  event_id: string;
  /**
   * Normalized type from C2's vocabulary; unknown when it cannot be mapped.
   */
  event_type: string;
  /**
   * Source fields that were not mapped (FR-02). Never columns listed in CON-20.
   */
  extra_fields?: {
    [k: string]: string | number | boolean | null | undefined;
  };
  /**
   * Host the event was observed on or is about; null if absent.
   */
  host?: string | null;
  /**
   * When the record was parsed (TD-12), UTC.
   */
  ingested_at: string;
  label: EventLabel;
  /**
   * Whether the account is privileged; null when the data does not say (OD-04).
   */
  privileged_user?: boolean | null;
  /**
   * Protocol; null if absent.
   */
  protocol?: string | null;
  provenance: Provenance;
  /**
   * Contract version.
   */
  schema_version?: "1.0";
  /**
   * Source IP; null if absent.
   */
  src_ip?: string | null;
  /**
   * Source port; null if absent.
   */
  src_port?: number | null;
  /**
   * Short human-readable description built by C2.
   */
  summary: string;
  /**
   * When the activity happened (event time), UTC. A record without one is rejected by C2 (FR-03).
   */
  timestamp: string;
  /**
   * Account name as in the source; null if absent.
   */
  user?: string | null;
}
/**
 * The dataset label of an event (OD-21, FR-41). The system never generates labels.
 *
 * This interface was referenced by `Event`'s JSON-Schema
 * via the `definition` "EventLabel".
 */
export interface EventLabel {
  /**
   * The dataset's attack-type column, kept as an attribute.
   */
  attack_type?: string | null;
  /**
   * Always dataset: labels come only from the data (FR-41).
   */
  origin?: "dataset";
  /**
   * The label exactly as in the dataset; null only when the record had none.
   */
  raw_value?: string | null;
  status: LabelStatus;
}
/**
 * Where the event came from (FR-05).
 *
 * This interface was referenced by `Event`'s JSON-Schema
 * via the `definition` "Provenance".
 */
export interface Provenance {
  /**
   * ID of the uploaded dataset.
   */
  dataset_id: string;
  /**
   * Row number, line number or original record ID in the source file.
   */
  record_ref: string;
  /**
   * Name of the source file.
   */
  source_file: string;
  /**
   * Format of the source, for example csv.
   */
  source_format: string;
}
