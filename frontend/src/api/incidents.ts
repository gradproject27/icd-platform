import { request } from "./client";
import { ApiError } from "./errors";
import type { IncidentList, IncidentSummary } from "./proposed";

/**
 * Header the dev-only stub server (dev/stub-server.mjs) sets on every incident answer. The real
 * API never sends it, so the list can say plainly when it shows example data.
 */
export const STUB_HEADER = "X-ICD-Stub";

export interface Answer<T> {
  data: T;
  /** True when the answer came from the stub server. */
  stub: boolean;
}

async function withStubFlag<T>(path: string, signal?: AbortSignal): Promise<Answer<T>> {
  let stub = false;
  const data = await request<T>(path, {
    signal,
    onResponse: (headers) => {
      stub = headers.get(STUB_HEADER) === "1";
    },
  });
  return { data, stub };
}

/** GET /incidents (proposed for C3). */
export async function listIncidents(signal?: AbortSignal): Promise<Answer<IncidentList>> {
  const answer = await withStubFlag<IncidentList>("/incidents", signal);
  if (!Array.isArray((answer.data as Partial<IncidentList> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected incident list.");
  }
  return answer;
}

/** GET /incidents/{incident_id} (proposed for C3). */
export function getIncident(incidentId: string, signal?: AbortSignal): Promise<Answer<IncidentSummary>> {
  return withStubFlag<IncidentSummary>(`/incidents/${encodeURIComponent(incidentId)}`, signal);
}
