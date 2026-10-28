// @vitest-environment node
/// <reference types="node" />
//
// The dev-only stub incidents (dev/stub-data/incidents.json): every incident is a valid Incident
// contract, the states follow the Week 2 table, and events and entities are exactly what the
// builder derives from C3's fixtures, so a fixture change without `npm run stub:build` fails.

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";
import { describe, expect, it } from "vitest";
import { buildStubData, OUTPUT_PATH, readSources, toText } from "../../dev/build-stub-incidents.mjs";
import type { Incident } from "../api/contracts";
import type { IncidentEntities } from "../api/proposed";

interface StubItem {
  fixture_label: string;
  incident: Incident;
  entities: IncidentEntities;
}

const SCHEMA_PATH = resolve(import.meta.dirname, "../../../contracts/schemas/incident.schema.json");
const addFormats = addFormatsModule as unknown as (ajv: Ajv2020) => Ajv2020;

const committedText = await readFile(OUTPUT_PATH, "utf8");
const items = (JSON.parse(committedText) as { items: StubItem[] }).items;
const byId = new Map(items.map((item) => [item.incident.incident_id, item.incident]));

describe("stub incidents", () => {
  it("are valid Incident contracts", async () => {
    const schema = JSON.parse(await readFile(SCHEMA_PATH, "utf8")) as object;
    const ajv = new Ajv2020({ allErrors: true, strict: false });
    addFormats(ajv);
    const validate = ajv.compile(schema);
    for (const { incident } of items) {
      expect(validate(incident), `${incident.incident_id}: ${ajv.errorsText(validate.errors)}`).toBe(true);
    }
  });

  it("have the IDs inc-stub-01 to inc-stub-13, one per fixture incident", async () => {
    expect(items.map((item) => [item.incident.incident_id, item.fixture_label])).toEqual([
      ["inc-stub-01", "A"],
      ["inc-stub-02", "G1"],
      ["inc-stub-03", "C2"],
      ["inc-stub-04", "D2a"],
      ["inc-stub-05", "C1"],
      ["inc-stub-06", "E"],
      ["inc-stub-07", "D1"],
      ["inc-stub-08", "F"],
      ["inc-stub-09", "G2a"],
      ["inc-stub-10", "G2b"],
      ["inc-stub-11", "D2b"],
      ["inc-stub-12", "G3"],
      ["inc-stub-13", "G4"],
    ]);
    const { expected } = (await readSources()) as { expected: { incidents: { label: string }[] } };
    const fixtureLabels = expected.incidents.map((incident) => incident.label).sort();
    expect(items.map((item) => item.fixture_label).sort()).toEqual(fixtureLabels);
  });

  it("show every lifecycle state at least once", () => {
    const statuses = new Set(items.map((item) => item.incident.status));
    expect([...statuses].sort()).toEqual(
      [
        "new",
        "under_analysis",
        "awaiting_human_decision",
        "response_in_progress",
        "escalated",
        "resolved",
        "closed",
      ].sort(),
    );
  });

  it("have no two equal risk scores, so the risk sort has no ties", () => {
    const scores = items.flatMap((item) => (item.incident.risk ? [item.incident.risk.score] : []));
    expect(new Set(scores).size).toBe(scores.length);
  });

  it("cover the states of the Week 2 table", () => {
    const row = (id: string) => {
      const incident = byId.get(id)!;
      return [incident.status, incident.risk?.level ?? null, incident.analysis_status];
    };
    expect(row("inc-stub-01")).toEqual(["awaiting_human_decision", "high", "succeeded"]);
    expect(row("inc-stub-02")).toEqual(["awaiting_human_decision", "high", "succeeded"]);
    expect(row("inc-stub-03")).toEqual(["awaiting_human_decision", "medium", "succeeded"]);
    expect(row("inc-stub-04")).toEqual(["awaiting_human_decision", "low", "succeeded"]);
    expect(row("inc-stub-05")).toEqual(["under_analysis", "medium", "failed"]);
    expect(row("inc-stub-06")).toEqual(["new", null, "not_started"]);
    expect(row("inc-stub-07")).toEqual(["resolved", "high", "succeeded"]);
    expect(row("inc-stub-08")).toEqual(["closed", "medium", "succeeded"]);
    expect(row("inc-stub-09")).toEqual(["response_in_progress", "high", "succeeded"]);
    expect(row("inc-stub-10")).toEqual(["escalated", "high", "succeeded"]);
    expect(row("inc-stub-11")).toEqual(["under_analysis", "low", "in_progress"]);
    expect(row("inc-stub-12")).toEqual(["awaiting_human_decision", "medium", "succeeded"]);
    expect(row("inc-stub-13")).toEqual(["new", null, "not_started"]);
    expect(byId.get("inc-stub-09")!.confidence).toBeGreaterThanOrEqual(0.75);
    expect(byId.get("inc-stub-10")!.confidence).toBeGreaterThanOrEqual(0.75);
    expect(byId.get("inc-stub-11")!.analysis_attempts).toBe(1);
    expect(byId.get("inc-stub-01")!.confidence).toBeGreaterThanOrEqual(0.75);
    expect(byId.get("inc-stub-02")!.confidence).toBeLessThan(0.75);
    expect(byId.get("inc-stub-07")!.confidence).toBeGreaterThanOrEqual(0.75);
    expect(byId.get("inc-stub-05")!.analysis_attempts).toBe(2);
  });

  it("keep the level, analysis and placeholder risk rules", () => {
    for (const { incident } of items) {
      const id = incident.incident_id;
      const succeeded = incident.analysis_status === "succeeded";
      expect(incident.confidence !== null, `${id}: confidence only when succeeded`).toBe(succeeded);
      expect(incident.latest_report_id ?? null, `${id}: report only when succeeded`).toBe(
        succeeded ? `rpt-stub-${id.slice(-2)}` : null,
      );
      if (!incident.risk) continue;
      const { score, level, factors, config_version } = incident.risk;
      const expectedLevel = score >= 70 ? "high" : score >= 40 ? "medium" : "low";
      expect(level, `${id}: level matches the score (OD-05 bands)`).toBe(expectedLevel);
      expect(config_version).toBe("stub-risk-v0");
      const sum = factors.reduce((total, factor) => total + factor.contribution, 0);
      expect(Math.abs(sum - score), `${id}: contributions add up to the score`).toBeLessThanOrEqual(0.5);
    }
  });

  it("have events, times and entities exactly as built from the fixtures", async () => {
    const rebuilt = buildStubData(await readSources());
    expect(toText(rebuilt)).toBe(committedText.replace(/\r\n/g, "\n"));
  });

  it("list each entity once, sorted", () => {
    for (const { entities } of items) {
      for (const values of [entities.hosts, entities.users, entities.ips]) {
        expect(values).toEqual([...new Set(values)].sort());
      }
    }
  });
});
