import type { IncidentStatus, RiskLevel } from "../api/contracts";
import type { IncidentSummary } from "../api/proposed";

// Counts for the Overview page (SOC UI phase 3). They only count what GET /incidents returned;
// no score, level or state is computed or changed here.

export type LevelKey = RiskLevel | "none";

export const LEVEL_ORDER: LevelKey[] = ["high", "medium", "low", "none"];

export const STATUS_ORDER: IncidentStatus[] = [
  "new",
  "under_analysis",
  "awaiting_human_decision",
  "response_in_progress",
  "escalated",
  "resolved",
  "closed",
];

/** The status the incident list filters on: a missing status reads as "new", as on that page. */
export const statusOf = (item: IncidentSummary): IncidentStatus => item.incident.status ?? "new";

export function countByLevel(items: IncidentSummary[]): Record<LevelKey, number> {
  const counts: Record<LevelKey, number> = { high: 0, medium: 0, low: 0, none: 0 };
  for (const { incident } of items) counts[incident.risk?.level ?? "none"] += 1;
  return counts;
}

export function countByStatus(items: IncidentSummary[]): Record<IncidentStatus, number> {
  const counts = Object.fromEntries(STATUS_ORDER.map((status) => [status, 0])) as Record<IncidentStatus, number>;
  for (const item of items) counts[statusOf(item)] += 1;
  return counts;
}

/** Incidents awaiting a human decision, newest first event first (the list's default order). */
export function awaitingDecision(items: IncidentSummary[]): IncidentSummary[] {
  return items
    .filter((item) => statusOf(item) === "awaiting_human_decision")
    .sort((a, b) => {
      const diff = Date.parse(b.incident.first_event_at) - Date.parse(a.incident.first_event_at);
      return diff !== 0 && !Number.isNaN(diff) ? diff : a.incident.incident_id.localeCompare(b.incident.incident_id);
    });
}

export type TimeBucket = { start: number; count: number };
export type TimeSeries = { unit: "hour" | "day"; buckets: TimeBucket[] };

/** At most this many hourly buckets; a longer span is counted per day. */
export const MAX_HOUR_BUCKETS = 48;

const HOUR_MS = 3_600_000;

/**
 * Incidents per hour of their first event (dataset time, decision D10), in local time, with empty
 * hours filled in so gaps show. Per day when the span is longer than MAX_HOUR_BUCKETS hours.
 */
export function perTimeBucket(items: IncidentSummary[]): TimeSeries {
  const times = items.map(({ incident }) => Date.parse(incident.first_event_at)).filter((ms) => !Number.isNaN(ms));
  if (times.length === 0) return { unit: "hour", buckets: [] };

  const floorHour = (ms: number) => {
    const date = new Date(ms);
    date.setMinutes(0, 0, 0);
    return date.getTime();
  };
  const floorDay = (ms: number) => {
    const date = new Date(ms);
    date.setHours(0, 0, 0, 0);
    return date.getTime();
  };
  const first = floorHour(Math.min(...times));
  const last = floorHour(Math.max(...times));
  const unit = (last - first) / HOUR_MS + 1 > MAX_HOUR_BUCKETS ? "day" : "hour";
  const floor = unit === "hour" ? floorHour : floorDay;

  const counts = new Map<number, number>();
  for (const ms of times) counts.set(floor(ms), (counts.get(floor(ms)) ?? 0) + 1);

  const buckets: TimeBucket[] = [];
  const end = floor(Math.max(...times));
  for (let start = floor(Math.min(...times)); start <= end; ) {
    buckets.push({ start, count: counts.get(start) ?? 0 });
    const next = new Date(start);
    if (unit === "hour") next.setHours(next.getHours() + 1);
    else next.setDate(next.getDate() + 1);
    start = next.getTime();
  }
  return { unit, buckets };
}
