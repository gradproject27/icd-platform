/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * Machine-readable reason. The first group answers a request; the second fails a job.
 *
 * This interface was referenced by `Job`'s JSON-Schema
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
 * This interface was referenced by `Job`'s JSON-Schema
 * via the `definition` "JobKind".
 */
export type JobKind = "ingest" | "analysis";
/**
 * What a running job is doing now, for progress display. Set only while running.
 *
 * This interface was referenced by `Job`'s JSON-Schema
 * via the `definition` "JobStage".
 */
export type JobStage = "validating" | "parsing" | "storing" | "submitting" | "waiting_hpc" | "collecting";
/**
 * Where a job is. done and failed are final; a job never stays running forever.
 *
 * This interface was referenced by `Job`'s JSON-Schema
 * via the `definition` "JobState".
 */
export type JobState = "queued" | "running" | "done" | "failed";

/**
 * GET /jobs/{job_id}. Poll it about once a second until state is done or failed.
 */
export interface Job {
  /**
   * Analysis jobs: set exactly when done.
   */
  analysis?: AnalysisOutcome | null;
  /**
   * Runs so far; a lost worker's job is retried.
   */
  attempts: number;
  /**
   * Ingest jobs: progress while running, final when done, null otherwise.
   */
  counts?: IntakeCounts | null;
  created_at: string;
  /**
   * Set exactly when failed.
   */
  error?: ApiError | null;
  /**
   * Set when done or failed.
   */
  finished_at?: string | null;
  job_id: string;
  kind: JobKind;
  max_attempts: number;
  /**
   * Set exactly while running.
   */
  stage?: JobStage | null;
  /**
   * First time it ran.
   */
  started_at?: string | null;
  state: JobState;
  /**
   * Set exactly for ingest jobs.
   */
  upload_id?: string | null;
}
/**
 * Result of a finished analysis job. An invalid report is a result, not a job failure.
 *
 * This interface was referenced by `Job`'s JSON-Schema
 * via the `definition` "AnalysisOutcome".
 */
export interface AnalysisOutcome {
  /**
   * Set exactly when report_valid.
   */
  confidence?: number | null;
  evidence_package_id: string;
  generated_by: "mock" | "hpc" | "local";
  incident_id: string;
  /**
   * Why the report is not valid; empty when it is.
   */
  problems?: string[];
  /**
   * Set exactly when report_valid.
   */
  report_id?: string | null;
  /**
   * True when the report passed every check.
   */
  report_valid: boolean;
}
/**
 * C2's intake summary. No record disappears: every record read is stored or quarantined.
 *
 * This interface was referenced by `Job`'s JSON-Schema
 * via the `definition` "IntakeCounts".
 */
export interface IntakeCounts {
  events_stored: number;
  flagged: number;
  quarantined: number;
  /**
   * Quarantined records grouped by reason code.
   */
  quarantined_by_reason?: {
    /**
     * This interface was referenced by `undefined`'s JSON-Schema definition
     * via the `patternProperty` "^[a-z0-9_]+$".
     */
    [k: string]: number | undefined;
  };
  records_read: number;
  unflagged: number;
  unlabelled: number;
}
/**
 * This interface was referenced by `Job`'s JSON-Schema
 * via the `definition` "ApiError".
 */
export interface ApiError {
  code: ErrorCode;
  /**
   * Plain-language reason, safe to show to the user.
   */
  message: string;
}
