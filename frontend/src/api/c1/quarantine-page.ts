/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * GET /uploads/{upload_id}/quarantine: quarantined records in seq order.
 */
export interface QuarantinePage {
  items: QuarantinedRecord[];
  /**
   * Pass as ?after= for the next page; null on the last page.
   */
  next_after: number | null;
}
/**
 * A record that could not become an Event (FR-03), with its reason.
 *
 * This interface was referenced by `QuarantinePage`'s JSON-Schema
 * via the `definition` "QuarantinedRecord".
 */
export interface QuarantinedRecord {
  /**
   * Start of the original record, cut at 500 characters.
   */
  raw_excerpt?: string | null;
  /**
   * Plain-language reason.
   */
  reason: string;
  /**
   * C2's reason code, for example bad_timestamp.
   */
  reason_code: string;
  /**
   * Row or line reference, as in Provenance.
   */
  record_ref: string;
  /**
   * Position of the record in the file, from 1.
   */
  seq: number;
}
