// Clock maths for the server-owned response window (docs/response-workflow-spec.md section 7).
//
// The server owns the deadline. The browser never starts its own timer and never computes a
// deadline: it only estimates the server's current time as client clock + offset, where the
// offset is measured from the server_time the server sends.

// ISO 8601 with an explicit zone, as the server sends it (2026-11-02T09:15:30.250Z). A time
// without a zone would be read as local time, so it is rejected instead of guessed.
const ISO_WITH_ZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

/** Parses an ISO 8601 time to epoch milliseconds, or throws instead of returning NaN. */
export function parseIsoMs(value: string, field = "time"): number {
  const ms = typeof value === "string" && ISO_WITH_ZONE.test(value) ? Date.parse(value) : Number.NaN;
  if (Number.isNaN(ms)) {
    throw new Error(`Invalid ${field}: expected ISO 8601 with a time zone, got ${JSON.stringify(value)}`);
  }
  return ms;
}

/** Offset from a pushed event: server_time − receivedAt (spec section 7). */
export function offsetFromPush(serverTimeIso: string, receivedAtMs: number): number {
  return parseIsoMs(serverTimeIso, "server_time") - receivedAtMs;
}

/**
 * Offset from a REST read: server_time − midpoint of the request. The server read its clock
 * somewhere between sending and receiving, so the midpoint halves the error of a slow request.
 */
export function offsetFromRequest(serverTimeIso: string, sentAtMs: number, receivedAtMs: number): number {
  return parseIsoMs(serverTimeIso, "server_time") - (sentAtMs + receivedAtMs) / 2;
}

/** Remaining time: deadline_at − (clientNow + offset), never below 0. */
export function remainingMs(deadlineIso: string, offsetMs: number, clientNowMs: number): number {
  return Math.max(0, parseIsoMs(deadlineIso, "deadline_at") - (clientNowMs + offsetMs));
}

/** m:ss, rounded up to the next whole second, so 0:00 shows only when the time is really up. */
export function formatRemaining(ms: number): string {
  if (Number.isNaN(ms)) throw new Error("Invalid remaining time: NaN");
  const seconds = Math.ceil(Math.max(0, ms) / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** A server time shown in local time as YYYY-MM-DD HH:MM:SS (docs/wireframes.md section 5). */
export function formatLocalDateTime(iso: string): string {
  const d = new Date(parseIsoMs(iso));
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}
