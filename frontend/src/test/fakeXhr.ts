import { vi } from "vitest";

/**
 * A minimal fake XMLHttpRequest for upload tests. No test makes a real network call. Each
 * request the code opens is in `requests`; the test drives it with progress(), respond() and
 * fail(), and the code under test may call abort().
 */
export class FakeXhr {
  static requests: FakeXhr[] = [];

  method = "";
  url = "";
  status = 0;
  responseText = "";
  body: unknown = null;
  aborted = false;
  readonly headers = new Map<string, string>();
  readonly upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXhr.requests.push(this);
  }

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string) {
    this.headers.set(name.toLowerCase(), value);
  }

  send(body: unknown) {
    this.body = body;
  }

  abort() {
    this.aborted = true;
    this.onabort?.();
  }

  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total } as ProgressEvent);
  }

  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = typeof body === "string" ? body : JSON.stringify(body);
    this.onload?.();
  }

  fail() {
    this.onerror?.();
  }
}

export function mockXhr() {
  FakeXhr.requests = [];
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  return FakeXhr.requests;
}
