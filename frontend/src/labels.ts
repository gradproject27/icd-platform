import type { IncidentStatus, RiskLevel } from "./api/contracts";

// The one place that maps contract enum values to UI labels. Typed with the generated enum types,
// so a value C3 adds to (or removes from) a schema is a compile error here until it is labelled.

export const INCIDENT_STATUS_LABELS: Record<IncidentStatus, string> = {
  new: "New",
  under_analysis: "Under Analysis",
  awaiting_human_decision: "Awaiting Human Decision",
  response_in_progress: "Response in Progress",
  escalated: "Escalated",
  resolved: "Resolved",
  closed: "Closed",
};

export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};
