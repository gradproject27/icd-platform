// Local test server for the T1-11 countdown prototype. DEV AND TEST ONLY: it plays the backend's
// role for the response window (docs/response-workflow-spec.md section 7) until the real API has
// one. It is never imported by src/ application code and is not in the production build.
//
//   npm run countdown:server                      port 8001, server clock = local clock
//   npm run countdown:server -- --skew-ms 90000   server clock 90 s ahead of the browser's
//
// Paths are the ones the backend would expose after the /api prefix is stripped:
//   GET  /response-windows/{incident_id}             read the window (never creates one)
//   POST /dev/response-windows/{incident_id}         open a window (test only)
//   POST /dev/response-windows/{incident_id}/decide  record a decision (test only)
//   WS   /ws/response-windows?incident_id=...        response_window.* events
//
// No authentication: the real channel checks the session cookie and the Origin header (A2.8).
//
// The response-window logic is the building block createResponseWindows(), which the stub server
// (dev/stub-server.mjs) reuses, so both serve the same windows the same way.

import { createServer } from "node:http";
import { pathToFileURL } from "node:url";
import { WebSocket, WebSocketServer } from "ws";

const REMINDER_BEFORE_MS = 30_000;

/**
 * The response windows of one server process: state, timers, the REST paths and the WebSocket
 * channel. handle() answers a response-window request, or returns null for any other path.
 */
export function createResponseWindows({ skewMs = 0, windowSeconds = 60, log = (line) => console.log(line) } = {}) {
  // Every time the server sends comes from this clock, never from Date.now() directly, so a
  // non-zero skew really tests the client's offset logic.
  const serverNow = () => Date.now() + skewMs;
  const iso = (ms) => new Date(ms).toISOString();

  const windows = new Map(); // incident_id -> window record
  const subscribers = new Map(); // incident_id -> Set<WebSocket>
  let nextWindow = 1;
  let wss = null;

  const snapshot = (w) => ({
    incident_id: w.incident_id,
    window_id: w.window_id,
    status: w.status,
    started_at: iso(w.startedAtMs),
    deadline_at: iso(w.deadlineAtMs),
    server_time: iso(serverNow()),
    recommended_scenario_id: w.recommended_scenario_id,
  });

  const remainingText = (incidentId) => {
    const w = windows.get(incidentId);
    return w && w.status === "open" ? ` remaining=${((w.deadlineAtMs - serverNow()) / 1000).toFixed(1)}s` : "";
  };

  function push(w, type, fields) {
    const event = { type, incident_id: w.incident_id, window_id: w.window_id, ...fields, server_time: iso(serverNow()) };
    const text = JSON.stringify(event);
    let sent = 0;
    for (const socket of subscribers.get(w.incident_id) ?? []) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(text);
        sent += 1;
      }
    }
    log(`${event.server_time} event ${type} ${w.incident_id} ${w.window_id} -> ${sent} socket(s)`);
  }

  function clearTimers(w) {
    clearTimeout(w.reminderTimer);
    clearTimeout(w.expiryTimer);
  }

  function scheduleExpiry(w) {
    w.expiryTimer = setTimeout(() => {
      // Timers can fire a little early; the deadline, not the timer, decides.
      if (serverNow() < w.deadlineAtMs) return scheduleExpiry(w);
      if (w.status !== "open") return;
      w.status = "expired";
      push(w, "response_window.expired", {});
    }, Math.max(0, w.deadlineAtMs - serverNow()));
  }

  function openWindow(incidentId) {
    const existing = windows.get(incidentId);
    if (existing && existing.status === "open") return { created: false, window: snapshot(existing) };
    if (existing) clearTimers(existing);

    const startedAtMs = serverNow();
    const w = {
      incident_id: incidentId,
      window_id: `win-${String(nextWindow++).padStart(4, "0")}`,
      status: "open",
      startedAtMs,
      deadlineAtMs: startedAtMs + windowSeconds * 1000,
      recommended_scenario_id: "S2",
    };
    windows.set(incidentId, w);

    const reminderAtMs = w.deadlineAtMs - REMINDER_BEFORE_MS;
    if (reminderAtMs > startedAtMs) {
      w.reminderTimer = setTimeout(() => {
        if (w.status === "open") push(w, "response_window.reminder", { deadline_at: iso(w.deadlineAtMs) });
      }, reminderAtMs - serverNow());
    }
    scheduleExpiry(w);

    push(w, "response_window.opened", {
      started_at: iso(w.startedAtMs),
      deadline_at: iso(w.deadlineAtMs),
      recommended_scenario_id: w.recommended_scenario_id,
    });
    return { created: true, window: snapshot(w) };
  }

  function decide(incidentId) {
    const w = windows.get(incidentId);
    if (!w) return [404, { detail: "no response window" }];
    // Same rule as the backend's conditional update: only while server time < deadline_at.
    if (w.status === "open" && serverNow() < w.deadlineAtMs) {
      w.status = "decided";
      clearTimers(w);
      push(w, "response_window.decided", {});
      return [200, snapshot(w)];
    }
    if (w.status === "decided") return [409, { detail: "window already decided" }];
    return [409, { detail: "window expired" }];
  }

  /** [status, body, incidentId] for a response-window path, or null for any other path. */
  function handle(method, parts) {
    if (method === "GET" && parts.length === 2 && parts[0] === "response-windows") {
      const incidentId = parts[1];
      const w = windows.get(incidentId);
      return w ? [200, snapshot(w), incidentId] : [404, { detail: "no response window" }, incidentId];
    }
    if (method === "POST" && parts[0] === "dev" && parts[1] === "response-windows" && parts[2]) {
      const incidentId = parts[2];
      if (parts.length === 3) {
        const { created, window } = openWindow(incidentId);
        return created
          ? [201, window, incidentId]
          : [409, { detail: "a response window is already open" }, incidentId];
      }
      if (parts.length === 4 && parts[3] === "decide") return [...decide(incidentId), incidentId];
      return [404, { detail: "not found" }, incidentId];
    }
    return null;
  }

  /** Serves the WebSocket channel /ws/response-windows on this HTTP server. */
  function attach(server) {
    wss = new WebSocketServer({ server, path: "/ws/response-windows" });
    wss.on("connection", (socket, req) => {
      const incidentId = new URL(req.url ?? "/", "http://localhost").searchParams.get("incident_id");
      if (!incidentId) {
        socket.close(1008, "incident_id is required");
        return;
      }
      if (!subscribers.has(incidentId)) subscribers.set(incidentId, new Set());
      subscribers.get(incidentId).add(socket);
      log(`${iso(serverNow())} ws connected ${incidentId}`);
      socket.on("close", () => {
        subscribers.get(incidentId)?.delete(socket);
        log(`${iso(serverNow())} ws closed ${incidentId}`);
      });
    });
  }

  async function close() {
    for (const w of windows.values()) clearTimers(w);
    if (wss) {
      for (const socket of wss.clients) socket.terminate();
      await new Promise((resolve) => wss.close(resolve));
    }
  }

  /** The current snapshot of an incident's window, or null when it has none. */
  const snapshotOf = (incidentId) => {
    const w = windows.get(incidentId);
    return w ? snapshot(w) : null;
  };

  return { serverNow, iso, remainingText, openWindow, decide, snapshotOf, handle, attach, close };
}

export async function startCountdownServer({
  port = 0,
  skewMs = 0,
  windowSeconds = 60,
  log = (line) => console.log(line),
} = {}) {
  const responseWindows = createResponseWindows({ skewMs, windowSeconds, log });
  const { serverNow, iso } = responseWindows;

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);
    const [status, body, incidentId] = responseWindows.handle(req.method, parts) ?? [404, { detail: "not found" }, null];

    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify(body));
    log(`${iso(serverNow())} ${req.method} ${url.pathname} ${status}${responseWindows.remainingText(incidentId)}`);
  });
  responseWindows.attach(server);

  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  const actualPort = server.address().port;

  return {
    url: `http://127.0.0.1:${actualPort}`,
    port: actualPort,
    serverNow,
    openWindow: responseWindows.openWindow,
    async close() {
      await responseWindows.close();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

export function readFlag(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1) return fallback;
  const value = Number(process.argv[index + 1]);
  if (!Number.isFinite(value)) throw new Error(`${name} needs a number`);
  return value;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const options = {
    port: readFlag("--port", 8001),
    skewMs: readFlag("--skew-ms", 0),
    windowSeconds: readFlag("--window-seconds", 60),
  };
  const server = await startCountdownServer(options);
  console.log(
    `Countdown test server on ${server.url} (skew ${options.skewMs} ms, window ${options.windowSeconds} s). ` +
      `Open a window: curl.exe -X POST ${server.url}/dev/response-windows/inc-demo`,
  );
}
