// Types for dev/countdown-server.mjs, so the accuracy test can import it under strict TypeScript.

export interface CountdownServerOptions {
  /** 0 picks a free port. */
  port?: number;
  /** Server clock = Date.now() + skewMs. */
  skewMs?: number;
  windowSeconds?: number;
  log?: (line: string) => void;
}

export interface CountdownWindowSnapshot {
  incident_id: string;
  window_id: string;
  status: "open" | "decided" | "expired";
  started_at: string;
  deadline_at: string;
  server_time: string;
  recommended_scenario_id: string | null;
}

export interface CountdownServer {
  url: string;
  port: number;
  serverNow(): number;
  openWindow(incidentId: string): { created: boolean; window: CountdownWindowSnapshot };
  close(): Promise<void>;
}

export function startCountdownServer(options?: CountdownServerOptions): Promise<CountdownServer>;

export interface ResponseWindows {
  serverNow(): number;
  iso(ms: number): string;
  remainingText(incidentId: string | null): string;
  openWindow(incidentId: string): { created: boolean; window: CountdownWindowSnapshot };
  /** Same conditional rule as the backend: decided only while server time < deadline_at. */
  decide(incidentId: string): [number, unknown];
  snapshotOf(incidentId: string): CountdownWindowSnapshot | null;
  handle(method: string | undefined, parts: string[]): [number, unknown, string | null] | null;
  attach(server: import("node:http").Server): void;
  close(): Promise<void>;
}

/** The response-window building block shared by the countdown server and the stub server. */
export function createResponseWindows(options?: Omit<CountdownServerOptions, "port">): ResponseWindows;

export function readFlag(name: string, fallback: number): number;
