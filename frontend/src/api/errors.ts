/**
 * Why a request failed:
 * - network: fetch rejected (API down, DNS, connection refused);
 * - timeout: no complete answer within the client timeout;
 * - http: the API answered with a non-2xx status;
 * - parse: the body was not valid JSON, or not the expected shape.
 */
export type ApiErrorKind = "network" | "timeout" | "http" | "parse";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  /** HTTP status, set for kind "http". */
  readonly status?: number;
  /** Parsed JSON body of a non-2xx answer, when the body was JSON. */
  readonly body?: unknown;
  /** C1's machine-readable error.code (docs/api-upload-jobs.md), when the body has C1's shape. */
  readonly code?: string;

  constructor(
    kind: ApiErrorKind,
    message: string,
    options: { status?: number; body?: unknown; code?: string } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status;
    this.body = options.body;
    this.code = options.code;
  }
}

/** The {"error": {"code", "message"}} body C1 sends with every 4xx and 5xx, or undefined. */
export function c1ErrorOf(body: unknown): { code: string; message: string } | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const error = (body as Record<string, unknown>).error;
  if (typeof error !== "object" || error === null) return undefined;
  const { code, message } = error as Record<string, unknown>;
  if (typeof code !== "string" || typeof message !== "string" || message === "") return undefined;
  return { code, message };
}
