// @vitest-environment node
//
// Accuracy of the countdown against the real test server (dev/countdown-server.mjs), started
// in-process on a random port. The server's clock is skewed, so the offset logic is really used.

import { afterEach, describe, expect, it, vi } from "vitest";
import { startCountdownServer, type CountdownServer } from "../../dev/countdown-server.mjs";
import { offsetFromPush, offsetFromRequest, parseIsoMs, remainingMs } from "./clock";

const TARGET_MS = 1_000;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

let server: CountdownServer | null = null;

async function start(options: { skewMs?: number; windowSeconds?: number }) {
  server = await startCountdownServer({ ...options, log: () => undefined });
  // The real client, pointed at the test server instead of the /api proxy.
  vi.stubEnv("VITE_API_BASE_URL", server.url);
  vi.resetModules();
  const { getResponseWindow } = await import("../api/responseWindows");
  return { server, getResponseWindow };
}

function connect(url: string, incidentId: string, onEvent: (event: Record<string, string>, receivedAtMs: number) => void) {
  const socket = new WebSocket(`${url.replace("http:", "ws:")}/ws/response-windows?incident_id=${incidentId}`);
  socket.onmessage = (message) => onEvent(JSON.parse(String(message.data)) as Record<string, string>, Date.now());
  return new Promise<WebSocket>((resolve, reject) => {
    socket.onopen = () => resolve(socket);
    socket.onerror = () => reject(new Error("WebSocket did not connect"));
  });
}

afterEach(async () => {
  vi.unstubAllEnvs();
  await server?.close();
  server = null;
});

describe("countdown accuracy against the test server", () => {
  it.each([0, 90_000, -90_000])(
    "stays within 1 s of the server's remaining time with skew %i ms",
    async (skewMs) => {
      const { server, getResponseWindow } = await start({ skewMs });
      server.openWindow("inc-acc");

      const read = await getResponseWindow("inc-acc");
      const window = read.window;
      if (!window) throw new Error("no window");
      let offsetMs = offsetFromRequest(window.server_time, read.sentAtMs, read.receivedAtMs);
      const socket = await connect(server.url, "inc-acc", (event, receivedAtMs) => {
        offsetMs = offsetFromPush(event.server_time ?? "", receivedAtMs);
      });

      const deadlineMs = parseIsoMs(window.deadline_at);
      const differences: number[] = [];
      for (let sample = 0; sample < 5; sample += 1) {
        await sleep(400);
        const shown = remainingMs(window.deadline_at, offsetMs, Date.now());
        const truth = deadlineMs - server.serverNow();
        differences.push(Math.abs(shown - truth));
      }
      socket.close();

      const max = Math.max(...differences);
      console.log(`skew ${skewMs} ms: max |shown − server| = ${max.toFixed(1)} ms over 5 samples`);
      for (const difference of differences) expect(difference).toBeLessThan(TARGET_MS);
    },
    10_000,
  );

  it("a naive client that ignores the offset is about 90 s wrong with skew +90 s", async () => {
    const { server, getResponseWindow } = await start({ skewMs: 90_000 });
    server.openWindow("inc-naive");
    const { window } = await getResponseWindow("inc-naive");
    if (!window) throw new Error("no window");

    const naive = remainingMs(window.deadline_at, 0, Date.now());
    const truth = parseIsoMs(window.deadline_at) - server.serverNow();
    // The naive client sees deadline_at 90 s in its own future: about 150 s instead of 60 s.
    expect(Math.abs(naive - truth)).toBeGreaterThan(80_000);
  });

  it("reads the same window on refresh, and a second open while open is refused", async () => {
    const { server, getResponseWindow } = await start({});
    server.openWindow("inc-refresh");

    const first = await getResponseWindow("inc-refresh");
    const second = await getResponseWindow("inc-refresh");
    expect(second.window?.window_id).toBe(first.window?.window_id);
    expect(second.window?.deadline_at).toBe(first.window?.deadline_at);

    const again = await fetch(`${server.url}/dev/response-windows/inc-refresh`, { method: "POST" });
    expect(again.status).toBe(409);
    const third = await getResponseWindow("inc-refresh");
    expect(third.window?.deadline_at).toBe(first.window?.deadline_at);
  });

  it("sends response_window.expired once, at or after deadline_at", async () => {
    const { server } = await start({ windowSeconds: 2 });
    const expired: Record<string, string>[] = [];
    const socket = await connect(server.url, "inc-expiry", (event) => {
      if (event.type === "response_window.expired") expired.push(event);
    });
    const { window } = server.openWindow("inc-expiry");

    await sleep(2_600);
    socket.close();

    expect(expired).toHaveLength(1);
    expect(parseIsoMs(expired[0]?.server_time ?? "")).toBeGreaterThanOrEqual(parseIsoMs(window.deadline_at));
  }, 10_000);
});
