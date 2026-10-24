import { describe, expect, it } from "vitest";
import { HEALTH_DEGRADED, HEALTH_OK, jsonResponse, mockFetch } from "../test/fetch";
import { getHealth } from "./health";

describe("getHealth", () => {
  it("returns ok on a 200 answer", async () => {
    const fetchMock = mockFetch();
    fetchMock.mockResolvedValue(jsonResponse(HEALTH_OK));

    await expect(getHealth()).resolves.toEqual(HEALTH_OK);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/health");
  });

  it("treats a 503 with the degraded body as a valid answer, not an error", async () => {
    mockFetch().mockResolvedValue(jsonResponse(HEALTH_DEGRADED, 503));

    await expect(getHealth()).resolves.toEqual(HEALTH_DEGRADED);
  });

  it("still fails on a 503 without the degraded body", async () => {
    mockFetch().mockResolvedValue(new Response("Service Unavailable", { status: 503 }));

    await expect(getHealth()).rejects.toMatchObject({ kind: "http", status: 503 });
  });
});
