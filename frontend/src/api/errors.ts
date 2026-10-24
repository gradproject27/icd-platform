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

  constructor(kind: ApiErrorKind, message: string, options: { status?: number; body?: unknown } = {}) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options.status;
    this.body = options.body;
  }
}
