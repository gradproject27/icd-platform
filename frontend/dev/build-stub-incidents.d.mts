// Types for dev/build-stub-incidents.mjs, so the stub-data test can import it under strict TypeScript.

export const FIXTURES_DIR: string;
export const OVERLAY_PATH: string;
export const OUTPUT_PATH: string;

export interface StubSources {
  expected: unknown;
  events: unknown;
  overlay: unknown;
}

export function buildStubData(sources: StubSources): unknown;
export function readSources(): Promise<StubSources>;
export function toText(data: unknown): string;
