/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * GET /incidents/{incident_id}/events/{event_id}/original: the line the event came from.
 */
export interface OriginalRecord {
  event_id: string;
  /**
   * The original line as uploaded, without its line break.
   */
  line: string;
  record_ref: string;
  source_file: string;
}
