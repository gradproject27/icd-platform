import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import errorNotFound from "../../../docs/api/examples/error-not-found.json";
import jobDone from "../../../docs/api/examples/job-ingest-done.json";
import jobFailed from "../../../docs/api/examples/job-ingest-failed.json";
import jobQueued from "../../../docs/api/examples/job-ingest-queued.json";
import jobRunning from "../../../docs/api/examples/job-ingest-running.json";
import { jsonResponse, mockFetch } from "../test/fetch";
import { JOB_POLL_INTERVAL_MS, useJob } from "./useJob";

async function tick() {
  await act(() => vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS));
}

async function firstPoll() {
  await act(() => vi.advanceTimersByTimeAsync(0));
}

describe("useJob", () => {
  it("polls once a second and stops at done", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(jobQueued))
      .mockResolvedValueOnce(jsonResponse(jobRunning))
      .mockResolvedValueOnce(jsonResponse(jobDone));

    const { result } = renderHook(() => useJob(jobQueued.job_id));
    await firstPoll();
    expect(result.current.job?.state).toBe("queued");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/jobs/${jobQueued.job_id}`);

    await tick();
    expect(result.current.job?.state).toBe("running");
    await tick();
    expect(result.current.job?.state).toBe("done");

    await tick();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("stops at failed", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch();
    fetchMock.mockImplementation(async () => jsonResponse(jobFailed));

    const { result } = renderHook(() => useJob(jobFailed.job_id));
    await firstPoll();
    await tick();
    await tick();

    expect(result.current.job?.state).toBe("failed");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the last job and keeps polling through a network error", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(jobRunning))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(jobDone));

    const { result } = renderHook(() => useJob(jobRunning.job_id));
    await firstPoll();
    await tick();
    expect(result.current.connectionLost).toBe(true);
    expect(result.current.job?.state).toBe("running");

    await tick();
    expect(result.current.connectionLost).toBe(false);
    expect(result.current.job?.state).toBe("done");
  });

  it("stops after three 404 answers in a row", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch();
    fetchMock.mockImplementation(async () => jsonResponse(errorNotFound, 404));

    const { result } = renderHook(() => useJob("job-0000"));
    await firstPoll();
    await tick();
    expect(result.current.notFound).toBe(false);
    await tick();
    expect(result.current.notFound).toBe(true);

    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("polls nothing for a null job ID and stops on unmount", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch();
    fetchMock.mockImplementation(async () => jsonResponse(jobRunning));

    const { result, rerender, unmount } = renderHook(({ id }) => useJob(id), {
      initialProps: { id: null as string | null },
    });
    await tick();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.job).toBeNull();

    rerender({ id: jobRunning.job_id });
    await firstPoll();
    unmount();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
