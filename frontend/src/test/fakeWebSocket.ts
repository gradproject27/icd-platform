import { vi } from "vitest";

/** A WebSocket stand-in the test drives by hand: open(), emit(event) and drop(). */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  readonly url: string;
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances.at(-1);
    if (!socket) throw new Error("No WebSocket was created");
    return socket;
  }

  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  emit(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }

  /** The connection is lost (server stopped, network down). */
  drop() {
    this.readyState = 3;
    this.onclose?.(new CloseEvent("close"));
  }

  close() {
    this.readyState = 3;
  }
}

/** Replaces the global WebSocket for one test. */
export function mockWebSocket() {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
}
