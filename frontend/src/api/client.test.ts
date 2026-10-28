import { describe, expect, it, vi } from "vitest";
import { jsonResponse, mockFetch } from "../test/fetch";
import { REQUEST_TIMEOUT_MS, request } from "./client";
import { ApiError } from "./errors";

describe("request", () => {
  it("returns the parsed JSON of a 200 answer, on the same origin", async () => {
    const fetchMock = mockFetch();
    fetchMock.mockResolvedValue(jsonResponse({ hello: "world" }));

    await expect(request<{ hello: string }>("/thing")).resolves.toEqual({ hello: "world" });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/thing");
    expect(init?.credentials).toBe("same-origin");
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("turns a 503 JSON answer into an http ApiError with status and body", async () => {
    mockFetch().mockResolvedValue(jsonResponse({ status: "degraded" }, 503));

    const error = await request("/thing").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "http", status: 503, body: { status: "degraded" } });
  });

  it("uses C1's error.message and error.code when the error body has C1's shape", async () => {
    const body = { error: { code: "not_found", message: "No job with ID job-0000 exists." } };
    mockFetch().mockResolvedValue(jsonResponse(body, 404));

    await expect(request("/jobs/job-0000")).rejects.toMatchObject({
      kind: "http",
      status: 404,
      code: "not_found",
      message: "No job with ID job-0000 exists.",
      body,
    });
  });

  it("turns a fetch rejection into a network ApiError", async () => {
    mockFetch().mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(request("/thing")).rejects.toMatchObject({ kind: "network" });
  });

  it("aborts after the timeout and reports a timeout ApiError", async () => {
    vi.useFakeTimers();
    mockFetch().mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        }),
    );

    const assertion = expect(request("/slow")).rejects.toMatchObject({ kind: "timeout" });
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
    await assertion;
  });

  it("turns an invalid JSON body into a parse ApiError", async () => {
    mockFetch().mockResolvedValue(new Response("not json", { status: 200 }));

    await expect(request("/thing")).rejects.toMatchObject({ kind: "parse" });
  });
});
