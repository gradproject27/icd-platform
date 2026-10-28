/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Dataset an upload belongs to. Becomes Event.provenance.dataset_id.
 *
 * The same IDs as the sources in contracts/label-mapping.json, plus `fixture` for
 * synthetic test files that are already a JSON list of Events.
 *
 * This interface was referenced by `DatasetList`'s JSON-Schema
 * via the `definition` "DatasetSource".
 */
export type DatasetSource =
  "fixture" | "precinct6" | "unsw-nb15" | "cic-ids2017" | "loghub-bgl" | "loghub-thunderbird" | "otrf";

/**
 * GET /datasets: the choices for the upload form.
 */
export interface DatasetList {
  /**
   * Lower case, with the dot.
   */
  accepted_extensions: string[];
  items: Dataset[];
  max_upload_bytes: number;
}
/**
 * This interface was referenced by `DatasetList`'s JSON-Schema
 * via the `definition` "Dataset".
 */
export interface Dataset {
  dataset_id: DatasetSource;
  /**
   * Display name.
   */
  name: string;
  /**
   * False until C2's parser for this dataset is merged. An upload is still accepted, but its job fails with no_parser.
   */
  parser_available: boolean;
}
