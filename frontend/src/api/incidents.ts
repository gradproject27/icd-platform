import { request } from "./client";
import { ApiError } from "./errors";
import type { AnalysisReport, AuditRecord } from "./contracts";
import type { AuditTrail, IncidentEventList, IncidentList, IncidentSummary, OriginalRecord } from "./proposed";

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

/** GET /incidents. */
export async function listIncidents(signal?: AbortSignal): Promise<Answer<IncidentList>> {
  const answer = await withStubFlag<IncidentList>("/incidents", signal);
  if (!Array.isArray((answer.data as Partial<IncidentList> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected incident list.");
  }
  return answer;
}

/** GET /incidents/{incident_id}. */
export function getIncident(incidentId: string, signal?: AbortSignal): Promise<Answer<IncidentSummary>> {
  return withStubFlag<IncidentSummary>(`/incidents/${encodeURIComponent(incidentId)}`, signal);
}

/** GET /incidents/{incident_id}/events: the incident's events, oldest first. */
export async function getIncidentEvents(incidentId: string, signal?: AbortSignal): Promise<IncidentEventList> {
  const data = await request<IncidentEventList>(`/incidents/${encodeURIComponent(incidentId)}/events`, { signal });
  if (!Array.isArray((data as Partial<IncidentEventList> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected event list.");
  }
  return data;
}

/** GET /incidents/{incident_id}/events/{event_id}/original: the uploaded line (FR-05). */
export function getOriginalRecord(incidentId: string, eventId: string, signal?: AbortSignal): Promise<OriginalRecord> {
  return request<OriginalRecord>(
    `/incidents/${encodeURIComponent(incidentId)}/events/${encodeURIComponent(eventId)}/original`,
    { signal },
  );
}

/**
 * GET /incidents/{incident_id}/report: the stored AI report, or null when none is stored yet
 * (404 report_not_available). Any other error is thrown.
 */
export async function getReport(incidentId: string, signal?: AbortSignal): Promise<AnalysisReport | null> {
  try {
    return await request<AnalysisReport>(`/incidents/${encodeURIComponent(incidentId)}/report`, { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.code === "report_not_available") return null;
    throw error;
  }
}

/** GET /incidents/{incident_id}/audit: C5's audit records of the incident, in written order. */
export async function getAuditTrail(incidentId: string, signal?: AbortSignal): Promise<AuditRecord[]> {
  const data = await request<AuditTrail>(`/incidents/${encodeURIComponent(incidentId)}/audit`, { signal });
  if (!Array.isArray((data as Partial<AuditTrail> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected audit trail.");
  }
  return data.items;
}
