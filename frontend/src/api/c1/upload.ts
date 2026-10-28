/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Dataset an upload belongs to. Becomes Event.provenance.dataset_id.
 *
 * The same IDs as the sources in contracts/label-mapping.json, plus `fixture` for
 * synthetic test files that are already a JSON list of Events.
 *
 * This interface was referenced by `Upload`'s JSON-Schema
 * via the `definition` "DatasetSource".
 */
export type DatasetSource =
  "fixture" | "precinct6" | "unsw-nb15" | "cic-ids2017" | "loghub-bgl" | "loghub-thunderbird" | "otrf";

/**
 * GET /uploads/{upload_id}.
 */
export interface Upload {
  dataset_id: DatasetSource;
  /**
   * The name the file had on the user's machine. Display only; the server never uses it as a path.
   */
  filename: string;
  /**
   * The ingest job that processes this upload.
   */
  job_id: string;
  received_at: string;
  /**
   * SHA-256 of the file content, lower-case hex.
   */
  sha256: string;
  size_bytes: number;
  upload_id: string;
}
