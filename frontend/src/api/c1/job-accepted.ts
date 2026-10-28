/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * 202 answer of POST /analysis-jobs.
 */
export interface JobAccepted {
  job_id: string;
  /**
   * Path of GET /jobs/{job_id}, without /api.
   */
  status_url: string;
}
