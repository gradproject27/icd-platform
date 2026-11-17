import type { IncidentSummary } from "../api/proposed";

// The review queue's groups (S8-D10), from the table in response-workflow-spec.md section 5.
// Nothing is computed: level, confidence and status are the API's.

export interface ReviewGroup {
  id: string;
  title: string;
  note: string;
  items: IncidentSummary[];
}

/** Oldest first event first, so nothing waits for ever at the bottom of the list. */
const oldestFirst = (a: IncidentSummary, b: IncidentSummary) =>
  Date.parse(a.incident.first_event_at) - Date.parse(b.incident.first_event_at) ||
  a.incident.incident_id.localeCompare(b.incident.incident_id);

/** The spec section 5 groups, and the escalated incidents (T09, T11). */
export function reviewGroups(items: IncidentSummary[]): { groups: ReviewGroup[]; escalated: IncidentSummary[]; other: number } {
  const waiting = items.filter(({ incident }) => incident.status === "awaiting_human_decision");
  const level = (summary: IncidentSummary) => summary.incident.risk?.level ?? null;
  const lowConfidence = (summary: IncidentSummary) => (summary.incident.confidence ?? 0) < 0.75;
  const medium = waiting.filter((s) => level(s) === "medium");
  const highNoTimer = waiting.filter((s) => level(s) === "high" && lowConfidence(s));
  const low = waiting.filter((s) => level(s) === "low");
  return {
    groups: [
      { id: "medium", title: "Medium risk", note: "Review (FR-25). No timer and no automatic action.", items: medium.sort(oldestFirst) },
      {
        id: "high",
        title: "High risk, confidence below 0.75",
        note: "No response window: the confidence gate was not met. No automatic action.",
        items: highNoTimer.sort(oldestFirst),
      },
      { id: "low", title: "Low risk", note: "Recorded and listed. No notification and no automatic action.", items: low.sort(oldestFirst) },
    ],
    escalated: items.filter(({ incident }) => incident.status === "escalated").sort(oldestFirst),
    other: waiting.length - medium.length - highNoTimer.length - low.length,
  };
}
