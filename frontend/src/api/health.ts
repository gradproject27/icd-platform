import { request } from "./client";
import { ApiError } from "./errors";

/**
 * Body of GET /health. Hand-written because /health is not one of the six shared contracts;
 * it mirrors backend/app/main.py, which answers 200 when the database is reachable and 503 with
 * {"status": "degraded", "database": "unavailable"} when it is not.
 */
export interface HealthResponse {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
}

/** A 503 with the degraded body is a valid answer (the API is up, the database is not). */
export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  let body: unknown;
  try {
    body = await request<unknown>("/health", { signal });
  } catch (error) {
    if (error instanceof ApiError && error.kind === "http" && error.status === 503 && isHealthResponse(error.body)) {
      return error.body;
    }
    throw error;
  }
  if (!isHealthResponse(body)) {
    throw new ApiError("parse", "The ICD API sent an unexpected health response.");
  }
  return body;
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const { status, database } = value as Record<string, unknown>;
  return (status === "ok" || status === "degraded") && (database === "ok" || database === "unavailable");
}
