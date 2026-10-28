/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Machine-readable reason. The first group answers a request; the second fails a job.
 *
 * This interface was referenced by `ErrorResponse`'s JSON-Schema
 * via the `definition` "ErrorCode".
 */
export type ErrorCode =
  | "validation_error"
  | "dataset_unknown"
  | "file_empty"
  | "file_too_large"
  | "format_not_accepted"
  | "invalid_evidence"
  | "not_found"
  | "report_not_available"
  | "no_parser"
  | "parse_failed"
  | "counts_mismatch"
  | "storage_failed"
  | "worker_lost"
  | "unmasked_evidence"
  | "hpc_unreachable"
  | "hpc_timeout"
  | "hpc_job_failed"
  | "report_missing"
  | "internal_error";

/**
 * Body of every 4xx and 5xx answer.
 */
export interface ErrorResponse {
  error: ApiError;
}
/**
 * This interface was referenced by `ErrorResponse`'s JSON-Schema
 * via the `definition` "ApiError".
 */
export interface ApiError {
  code: ErrorCode;
  /**
   * Plain-language reason, safe to show to the user.
   */
  message: string;
}
