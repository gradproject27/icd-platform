// @vitest-environment node
/// <reference types="node" />
//
// The dev-only stub server (dev/stub-server.mjs), started in-process on a random port.

import { createHash } from "node:crypto";
import { createServer, type Server } from "node:http";
import { afterEach, describe, expect, it } from "vitest";
import { startStubServer, type StubServer } from "../../dev/stub-server.mjs";

let stub: StubServer | null = null;
let upstream: Server | null = null;

afterEach(async () => {
  await stub?.close();
  stub = null;
  if (upstream) {
    const server = upstream;
    upstream = null;
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});

async function start(api: string | null = null) {
  stub = await startStubServer({ api, log: () => undefined });
  return stub;
}

/** A tiny stand-in for the real API: echoes the method, path, content type and body hash. */
async function startUpstream(): Promise<string> {
  upstream = createServer((req, res) => {
    const hash = createHash("sha256");
    let size = 0;
    req.on("data", (chunk: Buffer) => {
      hash.update(chunk);
      size += chunk.length;
    });
    req.on("end", () => {
      res.writeHead(req.url === "/health" ? 200 : 202, { "Content-Type": "application/json", "X-Upstream": "yes" });
      res.end(
        JSON.stringify({
          method: req.method,
          path: req.url,
          contentType: req.headers["content-type"] ?? null,
          size,
          sha256: hash.digest("hex"),
        }),
      );
    });
  });
  await new Promise<void>((resolve) => upstream!.listen(0, "127.0.0.1", resolve));
  const address = upstream.address();
  if (address === null || typeof address === "string") throw new Error("no port");
  return `http://127.0.0.1:${address.port}`;
}

interface Summary {
  incident: { incident_id: string; first_event_at: string };
  entities: unknown;
}

describe("stub server", () => {
  it("lists 13 stub incidents, newest first, with X-ICD-Stub: 1", async () => {
    const { url } = await start();
    const response = await fetch(`${url}/incidents`);
    expect(response.status).toBe(200);
    expect(response.headers.get("x-icd-stub")).toBe("1");
    const { items } = (await response.json()) as { items: Summary[] };
    expect(items).toHaveLength(13);
    const times = items.map((item) => Date.parse(item.incident.first_event_at));
    expect(times).toEqual([...times].sort((a, b) => b - a));
    expect(Object.keys(items[0]!).sort()).toEqual(["entities", "incident"]);
  });

  it("returns one incident, and 404 in C1's error shape for an unknown ID", async () => {
    const { url } = await start();
    const found = await fetch(`${url}/incidents/inc-stub-03`);
    expect(found.headers.get("x-icd-stub")).toBe("1");
    expect(((await found.json()) as Summary).incident.incident_id).toBe("inc-stub-03");

    const missing = await fetch(`${url}/incidents/inc-nope`);
    expect(missing.status).toBe(404);
    expect(await missing.json()).toEqual({
      error: { code: "not_found", message: "No incident with ID inc-nope exists." },
    });
  });

  it("answers 502 in C1's error shape for other paths when there is no real API", async () => {
    const { url } = await start();
    const response = await fetch(`${url}/health`);
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({
      error: { code: "internal_error", message: "The stub server has no real API to forward to." },
    });
  });

  it("forwards other paths and upload bodies to --api unchanged", async () => {
    const api = await startUpstream();
    const { url } = await start(api);

    const health = await fetch(`${url}/health`);
    expect(health.status).toBe(200);
    expect(health.headers.get("x-upstream")).toBe("yes");
    expect(await health.json()).toMatchObject({ method: "GET", path: "/health" });

    const body = new Uint8Array(300_000).map((_, index) => index % 251);
    const contentType = "multipart/form-data; boundary=test-boundary";
    const upload = await fetch(`${url}/uploads?x=1`, {
      method: "POST",
      headers: { "Content-Type": contentType },
      body,
    });
    expect(upload.status).toBe(202);
    expect(await upload.json()).toEqual({
      method: "POST",
      path: "/uploads?x=1",
      contentType,
      size: body.length,
      sha256: createHash("sha256").update(body).digest("hex"),
    });
  });

  it("serves the response windows as in T1-11", async () => {
    const { url } = await start();
    expect((await fetch(`${url}/response-windows/inc-stub-01`)).status).toBe(404);

    const socket = new WebSocket(`${url.replace("http:", "ws:")}/ws/response-windows?incident_id=inc-stub-01`);
    const events: string[] = [];
    socket.onmessage = (message) => events.push((JSON.parse(String(message.data)) as { type: string }).type);
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => resolve();
      socket.onerror = () => reject(new Error("WebSocket did not connect"));
    });

    const opened = await fetch(`${url}/dev/response-windows/inc-stub-01`, { method: "POST" });
    expect(opened.status).toBe(201);
    const window = (await opened.json()) as { status: string; deadline_at: string; started_at: string };
    expect(window.status).toBe("open");
    expect(Date.parse(window.deadline_at) - Date.parse(window.started_at)).toBe(60_000);

    expect((await fetch(`${url}/response-windows/inc-stub-01`)).status).toBe(200);
    expect((await fetch(`${url}/dev/response-windows/inc-stub-01`, { method: "POST" })).status).toBe(409);
    expect((await fetch(`${url}/dev/response-windows/inc-stub-01/decide`, { method: "POST" })).status).toBe(200);

    await new Promise((resolve) => setTimeout(resolve, 100));
    socket.close();
    expect(events).toEqual(["response_window.opened", "response_window.decided"]);
  });
});
