import type { AnalysisStatus, IncidentStatus, RiskLevel, ScenarioId } from "./api/contracts";

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

export const ANALYSIS_STATUS_LABELS: Record<AnalysisStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  succeeded: "Succeeded",
  failed: "Failed",
};

// Simulated response catalogue v0 (docs/response-workflow-spec.md section 9). Every scenario is a
// simulation; screens add the SIMULATED label next to it.
export const SCENARIO_LABELS: Record<ScenarioId, string> = {
  S1: "Keep the host isolated and flag it for investigation",
  S2: "Isolate the host and block the source IP",
  S3: "Isolate the host and disable the involved account",
  S4: "Release isolation and raise monitoring",
};
