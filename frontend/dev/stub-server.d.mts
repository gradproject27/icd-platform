// Types for dev/stub-server.mjs, so the stub-server test can import it under strict TypeScript.

import type { CountdownWindowSnapshot } from "./countdown-server.mjs";

export const STUB_HEADER: string;

export interface StubServerOptions {
  /** 0 picks a free port. */
  port?: number;
  /** Response-window clock = Date.now() + skewMs. */
  skewMs?: number;
  windowSeconds?: number;
  /** Real API that every non-stub path is forwarded to; null answers 502. */
  api?: string | null;
  /** Defaults to dev/stub-data/incidents.json. */
  dataPath?: string;
  /** Incidents that get an open response window at start (the command line opens inc-stub-01). */
  openWindows?: string[];
  /** Delay before an approved simulated action becomes simulated_succeeded (default 3000). */
  executeMs?: number;
  log?: (line: string) => void;
}

export interface StubServer {
  url: string;
  port: number;
  serverNow(): number;
  openWindow(incidentId: string): { created: boolean; window: CountdownWindowSnapshot };
  close(): Promise<void>;
}

export function startStubServer(options?: StubServerOptions): Promise<StubServer>;
