import { describe, expect, it } from "vitest";
import stubData from "../../dev/stub-data/incidents.json";
import type { IncidentSummary } from "../api/proposed";
import { awaitingDecision, countByLevel, countByStatus, MAX_HOUR_BUCKETS, perTimeBucket } from "./metrics";

const items = stubData.items.map(({ incident, entities }) => ({ incident, entities })) as IncidentSummary[];

/** A copy of the first stub incident with some fields replaced. */
function make(id: string, changes: Partial<IncidentSummary["incident"]>): IncidentSummary {
  const base = items[0]!;
  return { ...base, incident: { ...base.incident, incident_id: id, ...changes } };
}

describe("overview metrics", () => {
  it("counts the stub incidents by risk level, unscored apart", () => {
    expect(countByLevel(items)).toEqual({ high: 5, medium: 4, low: 2, none: 2 });
  });

  it("counts the stub incidents by state, every state present", () => {
    expect(countByStatus(items)).toEqual({
      new: 2,
      under_analysis: 2,
      awaiting_human_decision: 5,
      response_in_progress: 1,
      escalated: 1,
      resolved: 1,
      closed: 1,
    });
  });

  it("reads a missing state as New, like the incident list's filter", () => {
    const counts = countByStatus([make("x", { status: undefined })]);
    expect(counts.new).toBe(1);
  });

  it("lists the awaiting incidents newest first event first, ties by ID", () => {
    expect(awaitingDecision(items).map((item) => item.incident.incident_id)).toEqual([
      "inc-stub-12",
      "inc-stub-02",
      "inc-stub-04",
      "inc-stub-03",
      "inc-stub-01",
    ]);
    const tie = [
      make("inc-b", { status: "awaiting_human_decision", first_event_at: "2026-01-15T10:00:00Z" }),
      make("inc-a", { status: "awaiting_human_decision", first_event_at: "2026-01-15T10:00:00Z" }),
    ];
    expect(awaitingDecision(tie).map((item) => item.incident.incident_id)).toEqual(["inc-a", "inc-b"]);
  });

  it("counts per hour of the first event and fills empty hours", () => {
    const series = perTimeBucket([
      make("a", { first_event_at: "2026-01-15T10:05:00Z" }),
      make("b", { first_event_at: "2026-01-15T10:55:00Z" }),
      make("c", { first_event_at: "2026-01-15T13:30:00Z" }),
    ]);
    expect(series.unit).toBe("hour");
    expect(series.buckets.map((bucket) => bucket.count)).toEqual([2, 0, 0, 1]);
    expect(series.buckets[1]!.start - series.buckets[0]!.start).toBe(3_600_000);
  });

  it("counts per day when the span is longer than the hour limit", () => {
    const series = perTimeBucket([
      make("a", { first_event_at: "2026-01-10T12:00:00Z" }),
      make("b", { first_event_at: "2026-01-14T12:00:00Z" }),
    ]);
    expect(series.unit).toBe("day");
    expect(series.buckets.length).toBeGreaterThanOrEqual(5);
    expect(series.buckets.length).toBeLessThan(MAX_HOUR_BUCKETS);
    expect(series.buckets.reduce((sum, bucket) => sum + bucket.count, 0)).toBe(2);
  });

  it("skips unreadable times and returns no bucket for none", () => {
    expect(perTimeBucket([])).toEqual({ unit: "hour", buckets: [] });
    expect(perTimeBucket([make("a", { first_event_at: "not a time" })]).buckets).toEqual([]);
  });

  it("puts every stub incident in a bucket", () => {
    const total = perTimeBucket(items).buckets.reduce((sum, bucket) => sum + bucket.count, 0);
    expect(total).toBe(items.length);
  });
});
