import type { JobAccepted } from "./c1";
import { request } from "./client";
import { ApiError } from "./errors";
import type { AnalysisReport, AuditRecord } from "./contracts";
import type {
  AuditTrail,
  ContainmentList,
  EntityRiskList,
  IncidentEventList,
  IncidentKeyFacts,
  IncidentList,
  IncidentSummary,
  OriginalRecord,
  RecentDecisionList,
  ScenarioCatalogue,
} from "./proposed";

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

/** GET /incidents/{incident_id}/key-facts: start, assets and indicators computed by code (P1). */
export async function getKeyFacts(incidentId: string, signal?: AbortSignal): Promise<IncidentKeyFacts> {
  const data = await request<IncidentKeyFacts>(`/incidents/${encodeURIComponent(incidentId)}/key-facts`, { signal });
  if (!Array.isArray((data as Partial<IncidentKeyFacts> | null)?.attack_types)) {
    throw new ApiError("parse", "The ICD API sent unexpected key facts.");
  }
  return data;
}

/** GET /incidents/{incident_id}/containments: simulated IP blocks and their planned end (P2). */
export async function getContainments(incidentId: string, signal?: AbortSignal): Promise<ContainmentList> {
  const data = await request<ContainmentList>(`/incidents/${encodeURIComponent(incidentId)}/containments`, { signal });
  if (!Array.isArray((data as Partial<ContainmentList> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected containment list.");
  }
  return data;
}

/** GET /entity-risk: the read-only entity roll-up across incidents (P3), of one upload if given. */
export async function getEntityRisk(uploadId?: string, signal?: AbortSignal): Promise<EntityRiskList> {
  const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
  const data = await request<EntityRiskList>(`/entity-risk${query}`, { signal });
  if (!Array.isArray((data as Partial<EntityRiskList> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected entity risk list.");
  }
  return data;
}

/** GET /scenarios: the simulated catalogue with impact and how each scenario is reverted (P6). */
export async function getScenarios(signal?: AbortSignal): Promise<ScenarioCatalogue> {
  const data = await request<ScenarioCatalogue>("/scenarios", { signal });
  if (!Array.isArray((data as Partial<ScenarioCatalogue> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected scenario catalogue.");
  }
  return data;
}

/** GET /decisions/recent?hours=: analyst decisions and system selections, newest first (P6). */
export async function getRecentDecisions(hours = 72, signal?: AbortSignal): Promise<RecentDecisionList> {
  const data = await request<RecentDecisionList>(`/decisions/recent?hours=${hours}`, { signal });
  if (!Array.isArray((data as Partial<RecentDecisionList> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected decision list.");
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

/** A report as the report API shows it: un-masked for display, unless `masked` says otherwise. */
export interface ShownReport {
  report: AnalysisReport;
  /** True when the API answered with X-ICD-Report-Masked: 1 (some names are still tokens). */
  masked: boolean;
}

/** Header the report API sets when a host, user or IP token is still in the text (C4-D1). */
export const REPORT_MASKED_HEADER = "X-ICD-Report-Masked";

/**
 * GET /incidents/{incident_id}/report: the latest valid AI report, un-masked for display, or
 * null when none is stored yet (404 report_not_available). Any other error is thrown.
 */
export async function getShownReport(incidentId: string, signal?: AbortSignal): Promise<ShownReport | null> {
  let masked = false;
  try {
    const report = await request<AnalysisReport>(`/incidents/${encodeURIComponent(incidentId)}/report`, {
      signal,
      onResponse: (headers) => {
        masked = headers.get(REPORT_MASKED_HEADER) === "1";
      },
    });
    return { report, masked };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.code === "report_not_available") return null;
    throw error;
  }
}

/** The report alone, for pages that only cite it (detail, explanation). */
export async function getReport(incidentId: string, signal?: AbortSignal): Promise<AnalysisReport | null> {
  return (await getShownReport(incidentId, signal))?.report ?? null;
}

/** GET /incidents/{incident_id}/audit: C5's audit records of the incident, in written order. */
export async function getAuditTrail(incidentId: string, signal?: AbortSignal): Promise<AuditRecord[]> {
  const data = await request<AuditTrail>(`/incidents/${encodeURIComponent(incidentId)}/audit`, { signal });
  if (!Array.isArray((data as Partial<AuditTrail> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected audit trail.");
  }
  return data.items;
}

/**
 * POST /incidents/{incident_id}/analysis: queue a re-run of the AI analysis (C1, 202 JobAccepted).
 * An analysis already queued or running is returned instead of a second one.
 */
export function requestAnalysis(incidentId: string, signal?: AbortSignal): Promise<JobAccepted> {
  return request<JobAccepted>(`/incidents/${encodeURIComponent(incidentId)}/analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: false }),
    signal,
  });
}
