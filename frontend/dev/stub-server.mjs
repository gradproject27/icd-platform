// Dev-only stub server (decision D1). DEV AND TEST ONLY: it answers the HTTP paths the real API
// will have, so the dashboard runs before C3's incident endpoints exist. It is never imported by
// src/ application code and is not in the production build; the app only changes proxy target.
//
//   npm run stub:server                                    port 8001, no real API behind it
//   npm run stub:server -- --api http://localhost:8000     forward other paths to C1's API
//   npm run stub:server -- --skew-ms 90000                 skew the response-window clock
//
// Served here (paths as the API sees them, after /api is stripped):
//   GET /incidents, GET /incidents/{id}   dev/stub-data/incidents.json, with X-ICD-Stub: 1
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
  log = (line) => console.log(line),
} = {}) {
  // Read once at start. The served shape is the proposed IncidentSummary: { incident, entities }.
  const data = JSON.parse(await readFile(dataPath, "utf8"));
  const summaries = data.items
    .map(({ incident, entities }) => ({ incident, entities }))
    .sort(byNewestFirst);
  const byId = new Map(summaries.map((summary) => [summary.incident.incident_id, summary]));

  const responseWindows = createResponseWindows({ skewMs, windowSeconds, log });
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

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);

    if (req.method === "GET" && parts[0] === "incidents" && parts.length <= 2) {
      const stubHeaders = { [STUB_HEADER]: "1" };
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
  };
  const server = await startStubServer(options);
  console.log(
    `Stub server on ${server.url}: incidents from dev/stub-data/incidents.json (STUB DATA), ` +
      `response windows (skew ${options.skewMs} ms), other paths -> ${options.api ?? "502, no --api"}.`,
  );
}
