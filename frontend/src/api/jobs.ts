import type { Job } from "./c1";
import { request } from "./client";

/** GET /jobs/{job_id}: the status of an ingest or analysis job. */
export function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}`, { signal });
}
