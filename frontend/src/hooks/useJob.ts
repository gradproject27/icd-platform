import { useEffect, useState } from "react";
import type { Job } from "../api/c1";
import { ApiError } from "../api/errors";
import { getJob } from "../api/jobs";

export const JOB_POLL_INTERVAL_MS = 1_000;
/** A job that is still not found after this many polls in a row is reported as not found. */
export const JOB_NOT_FOUND_AFTER = 3;

export interface JobStatus {
  /** The last job the API returned; kept while the connection is lost. */
  job: Job | null;
  /** The last poll failed; the next one retries. */
  connectionLost: boolean;
  /** The API answered 404 three times in a row; polling has stopped. */
  notFound: boolean;
}

const INITIAL: JobStatus = { job: null, connectionLost: false, notFound: false };

const isFinal = (job: Job) => job.state === "done" || job.state === "failed";

/**
 * Polls GET /jobs/{job_id} once a second while the job is queued or running, and stops at done
 * or failed (docs/api-upload-jobs.md section 4). A null jobId polls nothing.
 */
export function useJob(jobId: string | null): JobStatus {
  // Tagged with the job it belongs to, so a new jobId starts from INITIAL without a reset render.
  const [status, setStatus] = useState<{ jobId: string | null } & JobStatus>({ jobId, ...INITIAL });

  useEffect(() => {
    if (jobId === null) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight: AbortController | null = null;
    let notFoundInARow = 0;

    const update = (change: Partial<JobStatus>) =>
      setStatus((previous) => ({
        ...(previous.jobId === jobId ? previous : { jobId, ...INITIAL }),
        ...change,
      }));

    const poll = async () => {
      const controller = new AbortController();
      inFlight = controller;
      try {
        const job = await getJob(jobId, controller.signal);
        if (stopped) return;
        notFoundInARow = 0;
        update({ job, connectionLost: false });
        if (isFinal(job)) return;
      } catch (error) {
        if (stopped) return;
        if (error instanceof ApiError && error.kind === "http" && error.status === 404) {
          notFoundInARow += 1;
          if (notFoundInARow >= JOB_NOT_FOUND_AFTER) {
            update({ notFound: true, connectionLost: false });
            return;
          }
        } else {
          notFoundInARow = 0;
          update({ connectionLost: true });
        }
      }
      timer = setTimeout(() => void poll(), JOB_POLL_INTERVAL_MS);
    };

    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      inFlight?.abort();
    };
  }, [jobId]);

  if (status.jobId !== jobId) return INITIAL;
  return { job: status.job, connectionLost: status.connectionLost, notFound: status.notFound };
}
