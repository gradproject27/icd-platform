import { ApiError, c1ErrorOf } from "./errors";

// Same origin only (auth-and-threat-model.md A2.14): /api is proxied to the backend by the Vite
// dev server and by nginx, so the browser never makes a cross-origin call.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export const REQUEST_TIMEOUT_MS = 5_000;

/**
 * The only place in the dashboard that calls fetch. Returns the parsed JSON body typed as T,
 * or throws an ApiError. If the caller's own signal aborts, its AbortError is rethrown as is.
 */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);

  const callerSignal = init.signal;
  const abortFromCaller = () => controller.abort();
  if (callerSignal?.aborted) controller.abort();
  callerSignal?.addEventListener("abort", abortFromCaller);

  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  let response: Response;
  let text: string;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      credentials: "same-origin",
      signal: controller.signal,
    });
    text = await response.text();
  } catch (cause) {
    if (timedOut) {
      throw new ApiError("timeout", `The ICD API did not answer within ${REQUEST_TIMEOUT_MS / 1000} seconds.`);
    }
    if (callerSignal?.aborted) throw cause;
    throw new ApiError("network", "Cannot reach the ICD API.");
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }

  if (!response.ok) {
    const body = parseJson(text);
    const c1Error = c1ErrorOf(body);
    throw new ApiError("http", c1Error?.message ?? `The ICD API answered with HTTP ${response.status}.`, {
      status: response.status,
      body,
      code: c1Error?.code,
    });
  }

  const data = parseJson(text);
  if (data === undefined) {
    throw new ApiError("parse", "The ICD API sent a response that is not valid JSON.");
  }
  return data as T;
}

export function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}
