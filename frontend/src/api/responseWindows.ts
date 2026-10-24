import { request } from "./client";
import type { ScenarioId } from "./contracts";
import { ApiError } from "./errors";

// Proposed shape from docs/response-workflow-spec.md section 7; move to the shared contracts when
// C3 adds it. The response window is not one of the six contracts (contracts-v1.md section 3.5).

export type ResponseWindowStatus = "open" | "decided" | "expired";

/** REST read of an incident's response window. All times are ISO 8601 UTC with milliseconds. */
export interface ResponseWindow {
  incident_id: string;
  window_id: string;
  status: ResponseWindowStatus;
  started_at: string;
  deadline_at: string;
  /** The server's clock when it answered, from the same database clock as deadline_at. */
  server_time: string;
  recommended_scenario_id: ScenarioId | null;
}

/** WebSocket events, with the fields of spec section 7. */
export type ResponseWindowEvent =
  | {
      type: "response_window.opened";
      incident_id: string;
      window_id: string;
      started_at: string;
      deadline_at: string;
      server_time: string;
      recommended_scenario_id: ScenarioId | null;
    }
  | { type: "response_window.reminder"; incident_id: string; window_id: string; deadline_at: string; server_time: string }
  | { type: "response_window.decided"; incident_id: string; window_id: string; server_time: string }
  | { type: "response_window.expired"; incident_id: string; window_id: string; server_time: string };

export interface ResponseWindowRead {
  /** null when the incident has no response window (HTTP 404). */
  window: ResponseWindow | null;
  /** Client clock when the request was sent and when the answer arrived, for the offset. */
  sentAtMs: number;
  receivedAtMs: number;
}

export async function getResponseWindow(incidentId: string, signal?: AbortSignal): Promise<ResponseWindowRead> {
  const sentAtMs = Date.now();
  let body: unknown;
  try {
    body = await request<unknown>(`/response-windows/${encodeURIComponent(incidentId)}`, { signal });
  } catch (error) {
    if (error instanceof ApiError && error.kind === "http" && error.status === 404) {
      return { window: null, sentAtMs, receivedAtMs: Date.now() };
    }
    throw error;
  }
  const receivedAtMs = Date.now();
  if (!isResponseWindow(body)) {
    throw new ApiError("parse", "The ICD API sent an unexpected response window.");
  }
  return { window: body, sentAtMs, receivedAtMs };
}

/** WebSocket URL on the page's own origin (A2.14): ws: or wss: to match the page. */
export function responseWindowSocketUrl(incidentId: string, location: Location = window.location): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}/ws/response-windows?incident_id=${encodeURIComponent(incidentId)}`;
}

/** Returns the event, or null for anything that is not a well-formed response_window event. */
export function parseResponseWindowEvent(data: unknown): ResponseWindowEvent | null {
  if (!isRecord(data) || !hasStrings(data, ["type", "incident_id", "window_id", "server_time"])) return null;
  switch (data.type) {
    case "response_window.opened":
      return hasStrings(data, ["started_at", "deadline_at"]) && isScenario(data.recommended_scenario_id)
        ? (data as ResponseWindowEvent)
        : null;
    case "response_window.reminder":
      return hasStrings(data, ["deadline_at"]) ? (data as ResponseWindowEvent) : null;
    case "response_window.decided":
    case "response_window.expired":
      return data as ResponseWindowEvent;
    default:
      return null;
  }
}

function isResponseWindow(value: unknown): value is ResponseWindow {
  return (
    isRecord(value) &&
    hasStrings(value, ["incident_id", "window_id", "started_at", "deadline_at", "server_time"]) &&
    (value.status === "open" || value.status === "decided" || value.status === "expired") &&
    isScenario(value.recommended_scenario_id)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function hasStrings(value: Record<string, unknown>, keys: string[]): boolean {
  return keys.every((key) => typeof value[key] === "string");
}

function isScenario(value: unknown): value is ScenarioId | null {
  return value === null || value === "S1" || value === "S2" || value === "S3" || value === "S4";
}
