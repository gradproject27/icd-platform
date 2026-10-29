// @vitest-environment node
/// <reference types="node" />
//
// The dev-only stub server (dev/stub-server.mjs), started in-process on a random port.

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer, type Server } from "node:http";
import { resolve } from "node:path";
import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";
import { afterEach, describe, expect, it } from "vitest";
import { startStubServer, type StubServer } from "../../dev/stub-server.mjs";
import type { DecisionRecord } from "../api/proposed";

const ACTION_SCHEMA_PATH = resolve(import.meta.dirname, "../../../contracts/schemas/response-action.schema.json");
const addFormats = addFormatsModule as unknown as (ajv: Ajv2020) => Ajv2020;

/** Every action the stub returns must be a valid ResponseAction contract. */
async function actionValidator() {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  const validate = ajv.compile(JSON.parse(await readFile(ACTION_SCHEMA_PATH, "utf8")) as object);
  return (action: unknown) => {
    expect(validate(action), ajv.errorsText(validate.errors)).toBe(true);
  };
}

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
    expect(Object.keys(items[0]!).sort()).toEqual(["entities", "incident", "recommended_scenario_id"]);
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

    // C1's dataset and job endpoints go to the real API too; only incidents and windows are stubbed.
    for (const path of ["/datasets", "/jobs/job-123"]) {
      const answer = await fetch(`${url}${path}`);
      expect(answer.headers.get("x-upstream")).toBe("yes");
      expect(answer.headers.get("x-icd-stub")).toBeNull();
      expect(await answer.json()).toMatchObject({ method: "GET", path });
    }

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

describe("stub server decision endpoints (proposed for C5)", () => {
  const post = (url: string, id: string, body: unknown) =>
    fetch(`${url}/incidents/${id}/decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

  it("records an approve during the open window, closes the window and moves the incident on", async () => {
    stub = await startStubServer({ openWindows: ["inc-stub-01"], executeMs: 10_000, log: () => undefined });
    const { url } = stub;
    expect((await fetch(`${url}/incidents/inc-stub-01/decision`)).status).toBe(404);

    const answer = await post(url, "inc-stub-01", {
      decision: "approve",
      scenario_id: "S2",
      window_id: "win-0001",
      comment: "Contain it",
    });
    expect(answer.status).toBe(201);
    expect(answer.headers.get("x-icd-stub")).toBe("1");
    expect(await answer.json()).toMatchObject({
      incident_id: "inc-stub-01",
      window_id: "win-0001",
      decision: "approve",
      scenario_id: "S2",
      comment: "Contain it",
      decided_by: "stub-analyst",
      incident_status: "response_in_progress",
    });

    const window = (await (await fetch(`${url}/response-windows/inc-stub-01`)).json()) as { status: string };
    expect(window.status).toBe("decided");
    expect(((await (await fetch(`${url}/incidents/inc-stub-01`)).json()) as Summary & { incident: { status: string } }).incident.status).toBe(
      "response_in_progress",
    );
    expect((await fetch(`${url}/incidents/inc-stub-01/decision`)).status).toBe(200);

    const again = await post(url, "inc-stub-01", { decision: "reject", scenario_id: null, window_id: null, comment: null });
    expect(again.status).toBe(409);
    expect(((await again.json()) as { error: { code: string } }).error.code).toBe("already_decided");
  });

  it("simulates the approved action, then resolves the incident after --execute-ms", async () => {
    const validAction = await actionValidator();
    stub = await startStubServer({ openWindows: ["inc-stub-01"], executeMs: 150, log: () => undefined });
    const { url } = stub;
    const readDecision = async () => (await (await fetch(`${url}/incidents/inc-stub-01/decision`)).json()) as DecisionRecord;
    const readStatus = async () =>
      ((await (await fetch(`${url}/incidents/inc-stub-01`)).json()) as { incident: { status: string } }).incident.status;

    const answer = (await (
      await post(url, "inc-stub-01", { decision: "select", scenario_id: "S3", window_id: "win-0001", comment: "Disable it" })
    ).json()) as DecisionRecord;
    validAction(answer.action);
    expect(answer.action).toMatchObject({
      action_id: "act-stub-inc-stub-01-1",
      incident_id: "inc-stub-01",
      window_id: "win-0001",
      scenario_id: "S3",
      state: "approved",
      simulated: true,
      trigger: "analyst_decision",
      target: { host: "db-01", ip: "10.10.1.21", account: "svc-db" },
      decided_by: "stub-analyst",
      decided_at: answer.decided_at,
      comment: "Disable it",
      executed_at: null,
    });
    expect(Date.parse(answer.action!.proposed_at)).toBeLessThanOrEqual(Date.parse(answer.decided_at));
    validAction((await readDecision()).action);
    expect(await readStatus()).toBe("response_in_progress");

    await new Promise((resolve) => setTimeout(resolve, 300));
    const done = await readDecision();
    validAction(done.action);
    expect(done.incident_status).toBe("resolved");
    expect(done.action).toMatchObject({ state: "simulated_succeeded", simulated: true });
    expect(Date.parse(done.action!.executed_at!)).toBeGreaterThanOrEqual(Date.parse(done.decided_at));
    expect(await readStatus()).toBe("resolved");
  });

  it("gives an action null target fields when the incident has no such entity", async () => {
    const validAction = await actionValidator();
    stub = await startStubServer({ log: () => undefined });
    const answer = (await (
      await post(stub.url, "inc-stub-02", { decision: "approve", scenario_id: "S1", window_id: null, comment: null })
    ).json()) as DecisionRecord;
    validAction(answer.action);
    expect(answer.action).toMatchObject({ window_id: null, comment: null, target: { host: "ws-80", ip: null, account: null } });
  });

  it("refuses a decision after the window expired with 409", async () => {
    stub = await startStubServer({ openWindows: ["inc-stub-01"], windowSeconds: 1, log: () => undefined });
    await new Promise((resolve) => setTimeout(resolve, 1_200));

    const answer = await post(stub.url, "inc-stub-01", {
      decision: "select",
      scenario_id: "S1",
      window_id: "win-0001",
      comment: null,
    });
    expect(answer.status).toBe(409);
    expect(((await answer.json()) as { error: { code: string } }).error.code).toBe("window_expired");
    expect((await fetch(`${stub.url}/incidents/inc-stub-01/decision`)).status).toBe(404);
  }, 5_000);

  it("records a reject without a window and keeps the incident awaiting", async () => {
    stub = await startStubServer({ log: () => undefined });
    const answer = await post(stub.url, "inc-stub-03", { decision: "reject", scenario_id: null, window_id: null, comment: null });
    expect(answer.status).toBe(201);
    expect(await answer.json()).toMatchObject({
      window_id: null,
      decision: "reject",
      incident_status: "awaiting_human_decision",
      action: null,
    });
  });

  it("validates the request", async () => {
    stub = await startStubServer({ log: () => undefined });
    const { url } = stub;
    const code = async (response: Response) => [response.status, ((await response.json()) as { error: { code: string } }).error.code];

    expect(await code(await post(url, "inc-stub-04", { decision: "approve", scenario_id: null, window_id: null, comment: null }))).toEqual([
      422,
      "validation_error",
    ]);
    expect(await code(await post(url, "inc-stub-02", { decision: "select", scenario_id: "S9", window_id: null, comment: null }))).toEqual([
      422,
      "validation_error",
    ]);
    expect(await code(await post(url, "inc-stub-02", { decision: "maybe", scenario_id: null, window_id: null, comment: null }))).toEqual([
      422,
      "validation_error",
    ]);
    expect(await code(await post(url, "inc-stub-07", { decision: "reject", scenario_id: null, window_id: null, comment: null }))).toEqual([
      409,
      "not_awaiting_decision",
    ]);
    expect(await code(await post(url, "inc-nope", { decision: "reject", scenario_id: null, window_id: null, comment: null }))).toEqual([
      404,
      "not_found",
    ]);
  });
});
