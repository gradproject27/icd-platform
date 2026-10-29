// Dev-only stub server (decision D1). DEV AND TEST ONLY: it answers the HTTP paths the real API
// will have, so the dashboard runs before C3's incident endpoints exist. It is never imported by
// src/ application code and is not in the production build; the app only changes proxy target.
//
//   npm run stub:server                                    port 8001, no real API behind it
//   npm run stub:server -- --api http://localhost:8000     forward other paths to C1's API
//   npm run stub:server -- --skew-ms 90000                 skew the response-window clock
//   npm run stub:server -- --no-window                     start without the inc-stub-01 window
//   npm run stub:server -- --execute-ms 3000               delay before a simulated action succeeds
//
// From the command line, a 60-second window opens for inc-stub-01 at start (the freeze case). To
// open it again later: curl.exe -X POST http://localhost:8001/dev/response-windows/inc-stub-01
//
// Served here (paths as the API sees them, after /api is stripped):
//   GET /incidents, GET /incidents/{id}   dev/stub-data/incidents.json, with X-ICD-Stub: 1
//   GET /incidents/{id}/decision, POST /incidents/{id}/decisions   the decision endpoints proposed
//     for C5 (src/api/proposed.ts), kept in memory; decided_by is "stub-analyst" (no login yet).
//     Approve or select records a SIMULATED ResponseAction in state approved; --execute-ms later it
//     is simulated_succeeded and the incident is resolved (spec section 8). Nothing real is touched.
//   response windows and /ws/response-windows   the countdown server's building block (T1-11)
// Every other path (/health, /datasets, /uploads, /jobs/...) is streamed to --api, or answers 502
// when there is no --api, so the health indicator honestly shows the API as unavailable.

import { readFile } from "node:fs/promises";
import { createServer, request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { pathToFileURL } from "node:url";
import { OUTPUT_PATH } from "./build-stub-incidents.mjs";
import { createResponseWindows, readFlag } from "./countdown-server.mjs";

export const STUB_HEADER = "X-ICD-Stub";

const byNewestFirst = (a, b) =>
  Date.parse(b.incident.first_event_at) - Date.parse(a.incident.first_event_at) ||
  a.incident.incident_id.localeCompare(b.incident.incident_id);

export async function startStubServer({
  port = 0,
  skewMs = 0,
  windowSeconds = 60,
  api = null,
  dataPath = OUTPUT_PATH,
  openWindows = [],
  executeMs = 3_000,
  log = (line) => console.log(line),
} = {}) {
  // Read once at start. The served shape is the proposed IncidentSummary.
  const data = JSON.parse(await readFile(dataPath, "utf8"));
  const summaries = data.items
    .map(({ incident, entities, recommended_scenario_id }) => ({ incident, entities, recommended_scenario_id }))
    .sort(byNewestFirst);
  const byId = new Map(summaries.map((summary) => [summary.incident.incident_id, summary]));
  const decisions = new Map(); // incident_id -> DecisionRecord
  const timers = new Set();
  let actionCount = 0;

  const responseWindows = createResponseWindows({ skewMs, windowSeconds, log });
  for (const incidentId of openWindows) responseWindows.openWindow(incidentId);
  const apiUrl = api ? new URL(api) : null;
  const stamp = () => new Date().toISOString();

  function sendJson(res, status, body, headers = {}) {
    res.writeHead(status, { "Content-Type": "application/json", ...headers });
    res.end(JSON.stringify(body));
  }

  function forward(req, res, url) {
    if (!apiUrl) {
      sendJson(res, 502, {
        error: { code: "internal_error", message: "The stub server has no real API to forward to." },
      });
      log(`${stamp()} ${req.method} ${url.pathname} 502 (no --api)`);
      return;
    }
    const target = new URL(url.pathname + url.search, apiUrl);
    const send = target.protocol === "https:" ? httpsRequest : httpRequest;
    const upstream = send(
      target,
      { method: req.method, headers: { ...req.headers, host: target.host } },
      (answer) => {
        res.writeHead(answer.statusCode ?? 502, answer.headers);
        answer.pipe(res);
        log(`${stamp()} ${req.method} ${url.pathname} ${answer.statusCode} (forwarded)`);
      },
    );
    upstream.on("error", () => {
      if (!res.headersSent) {
        sendJson(res, 502, { error: { code: "internal_error", message: "The real API did not answer." } });
      } else {
        res.destroy();
      }
      log(`${stamp()} ${req.method} ${url.pathname} 502 (forward failed)`);
    });
    // Streamed, not buffered: an upload can be hundreds of megabytes.
    req.pipe(upstream);
  }

  const stubHeaders = { [STUB_HEADER]: "1" };
  const stubError = (res, status, code, message) => sendJson(res, status, { error: { code, message } }, stubHeaders);

  /** POST /incidents/{id}/decisions: the rules of response-workflow-spec.md sections 8 and 10. */
  function decide(res, summary, body) {
    const incidentId = summary.incident.incident_id;
    const { decision, scenario_id: scenarioId = null, window_id: windowId = null, comment = null } = body ?? {};
    if (!["approve", "reject", "select"].includes(decision)) {
      return stubError(res, 422, "validation_error", "decision must be approve, reject or select.");
    }
    if (comment !== null && (typeof comment !== "string" || comment.trim() === "")) {
      return stubError(res, 422, "validation_error", "comment must be a non-empty text or null.");
    }
    if (decision === "approve" && (!summary.recommended_scenario_id || scenarioId !== summary.recommended_scenario_id)) {
      return stubError(res, 422, "validation_error", "Approve needs the recommended scenario, and this incident has none.");
    }
    if (decision === "select" && !["S1", "S2", "S3", "S4"].includes(scenarioId)) {
      return stubError(res, 422, "validation_error", "Select needs a catalogue scenario, S1 to S4.");
    }
    if (decision === "reject" && scenarioId !== null) {
      return stubError(res, 422, "validation_error", "Reject takes no scenario.");
    }
    if (decisions.has(incidentId)) {
      return stubError(res, 409, "already_decided", "A decision is already recorded for this incident.");
    }
    if (summary.incident.status !== "awaiting_human_decision") {
      return stubError(res, 409, "not_awaiting_decision", "This incident is not awaiting a decision.");
    }

    const window = responseWindows.snapshotOf(incidentId);
    if (window && window.status === "open") {
      // The same conditional rule as the backend: only while server time < deadline_at.
      const [status] = responseWindows.decide(incidentId);
      if (status !== 200) {
        return stubError(res, 409, "window_expired", `The response window expired at ${window.deadline_at}.`);
      }
    } else if (window && window.status === "expired") {
      return stubError(res, 409, "window_expired", `The response window expired at ${window.deadline_at}.`);
    }

    const now = responseWindows.iso(responseWindows.serverNow());
    const incidentStatus = decision === "reject" ? "awaiting_human_decision" : "response_in_progress";
    const recordWindowId = window && window.status !== "expired" ? window.window_id : windowId;
    const record = {
      incident_id: incidentId,
      window_id: recordWindowId,
      decision,
      scenario_id: scenarioId,
      comment,
      decided_by: "stub-analyst",
      decided_at: now,
      incident_status: incidentStatus,
      action: decision === "reject" ? null : simulatedAction(summary, scenarioId, recordWindowId, comment, now, window),
    };
    decisions.set(incidentId, record);
    summary.incident = { ...summary.incident, status: incidentStatus, updated_at: now };
    sendJson(res, 201, record, stubHeaders);
    if (record.action) scheduleExecution(summary, record);
  }

  /** A SIMULATED ResponseAction (contracts/schemas/response-action.schema.json), state approved. */
  function simulatedAction(summary, scenarioId, windowId, comment, now, window) {
    const incidentId = summary.incident.incident_id;
    const { hosts, ips, users } = summary.entities;
    actionCount += 1;
    return {
      schema_version: "1.0",
      action_id: `act-stub-${incidentId}-${actionCount}`,
      incident_id: incidentId,
      window_id: windowId,
      scenario_id: scenarioId,
      state: "approved",
      simulated: true,
      trigger: "analyst_decision",
      target: { host: hosts[0] ?? null, ip: ips[0] ?? null, account: users[0] ?? null },
      parameters: {},
      proposed_at: window ? window.started_at : now,
      decided_by: "stub-analyst",
      decided_at: now,
      comment,
      executed_at: null,
      failure_reason: null,
    };
  }

  /** After executeMs the simulated action succeeds and the incident is resolved (spec section 8). */
  function scheduleExecution(summary, record) {
    const timer = setTimeout(() => {
      timers.delete(timer);
      const executedAt = responseWindows.iso(responseWindows.serverNow());
      record.action = { ...record.action, state: "simulated_succeeded", executed_at: executedAt };
      record.incident_status = "resolved";
      summary.incident = { ...summary.incident, status: "resolved", updated_at: executedAt };
      log(`${executedAt} ${record.action.action_id} simulated_succeeded, ${summary.incident.incident_id} resolved (stub)`);
    }, executeMs);
    timers.add(timer);
  }

  function readJsonBody(req) {
    return new Promise((resolve) => {
      const chunks = [];
      req.on("data", (chunk) => chunks.push(chunk));
      req.on("end", () => {
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
        } catch {
          resolve(undefined);
        }
      });
    });
  }

  const server = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);

    if (parts[0] === "incidents" && parts.length === 3 && (parts[2] === "decision" || parts[2] === "decisions")) {
      const summary = byId.get(parts[1]);
      if (!summary) {
        stubError(res, 404, "not_found", `No incident with ID ${parts[1]} exists.`);
      } else if (req.method === "GET" && parts[2] === "decision") {
        const record = decisions.get(parts[1]);
        if (record) sendJson(res, 200, record, stubHeaders);
        else stubError(res, 404, "not_found", `No decision is recorded for incident ${parts[1]}.`);
      } else if (req.method === "POST" && parts[2] === "decisions") {
        const body = await readJsonBody(req);
        if (body === undefined) stubError(res, 422, "validation_error", "The body must be JSON.");
        else decide(res, summary, body);
      } else {
        stubError(res, 405, "validation_error", `${req.method} is not allowed here.`);
      }
      log(`${stamp()} ${req.method} ${url.pathname} ${res.statusCode} (stub)`);
      return;
    }

    if (req.method === "GET" && parts[0] === "incidents" && parts.length <= 2) {
      if (parts.length === 1) {
        sendJson(res, 200, { items: summaries }, stubHeaders);
        log(`${stamp()} GET ${url.pathname} 200 (stub, ${summaries.length} incidents)`);
        return;
      }
      const summary = byId.get(parts[1]);
      if (summary) {
        sendJson(res, 200, summary, stubHeaders);
      } else {
        sendJson(
          res,
          404,
          { error: { code: "not_found", message: `No incident with ID ${parts[1]} exists.` } },
          stubHeaders,
        );
      }
      log(`${stamp()} GET ${url.pathname} ${summary ? 200 : 404} (stub)`);
      return;
    }

    const windowAnswer = responseWindows.handle(req.method, parts);
    if (windowAnswer) {
      const [status, body, incidentId] = windowAnswer;
      sendJson(res, status, body);
      log(
        `${responseWindows.iso(responseWindows.serverNow())} ${req.method} ${url.pathname} ${status}` +
          responseWindows.remainingText(incidentId),
      );
      return;
    }

    forward(req, res, url);
  });
  responseWindows.attach(server);

  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  const actualPort = server.address().port;

  return {
    url: `http://127.0.0.1:${actualPort}`,
    port: actualPort,
    serverNow: responseWindows.serverNow,
    openWindow: responseWindows.openWindow,
    async close() {
      for (const timer of timers) clearTimeout(timer);
      timers.clear();
      await responseWindows.close();
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

function readText(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? null : (process.argv[index + 1] ?? null);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const options = {
    port: readFlag("--port", 8001),
    skewMs: readFlag("--skew-ms", 0),
    windowSeconds: readFlag("--window-seconds", 60),
    api: readText("--api"),
    openWindows: process.argv.includes("--no-window") ? [] : ["inc-stub-01"],
    executeMs: readFlag("--execute-ms", 3_000),
  };
  const server = await startStubServer(options);
  console.log(
    `Stub server on ${server.url}: incidents from dev/stub-data/incidents.json (STUB DATA), ` +
      `response windows (skew ${options.skewMs} ms${options.openWindows.length ? ", inc-stub-01 open" : ""}), ` +
      `other paths -> ${options.api ?? "502, no --api"}.`,
  );
}
