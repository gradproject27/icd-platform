import { vi } from "vitest";

/** Replaces the global fetch with a mock for one test. No test makes a real network call. */
export function mockFetch() {
  const fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const HEALTH_OK = { status: "ok", database: "ok" };
export const HEALTH_DEGRADED = { status: "degraded", database: "unavailable" };
