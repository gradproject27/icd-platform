import { request } from "./client";
import { ApiError } from "./errors";
import type { DecisionRecord, DecisionRequest } from "./proposed";

// Decision endpoints, proposed for C5 (see proposed.ts). Until C5 builds them, the dev-only stub
// server answers them.

/** GET /incidents/{incident_id}/decision: the recorded decision, or null when there is none (404). */
export async function getDecision(incidentId: string, signal?: AbortSignal): Promise<DecisionRecord | null> {
  try {
    return await request<DecisionRecord>(`/incidents/${encodeURIComponent(incidentId)}/decision`, { signal });
  } catch (error) {
    if (error instanceof ApiError && error.kind === "http" && error.status === 404) return null;
    throw error;
  }
}

/** POST /incidents/{incident_id}/decisions. Throws ApiError, for example 409 or 403. */
export function submitDecision(incidentId: string, body: DecisionRequest, signal?: AbortSignal): Promise<DecisionRecord> {
  return request<DecisionRecord>(`/incidents/${encodeURIComponent(incidentId)}/decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}
