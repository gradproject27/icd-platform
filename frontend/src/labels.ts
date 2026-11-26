import type {
  AnalysisStatus,
  AuditEventType,
  AuditResult,
  IncidentStatus,
  LinkKey,
  RiskFlag,
  RiskLevel,
  ScenarioId,
  UserRole,
} from "./api/contracts";

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

export const ROLE_LABELS: Record<UserRole, string> = {
  soc_analyst: "SOC Analyst",
  soc_manager: "SOC Manager",
  security_engineer: "Security Engineer",
  system_administrator: "System Administrator",
};

// Audit event types (response-workflow-spec.md section 11; auth doc). Records about simulated
// actions add the SIMULATED badge on screen.
export const AUDIT_EVENT_LABELS: Record<AuditEventType, string> = {
  status_changed: "Status changed",
  transition_refused: "Transition refused",
  "analysis.failed": "Analysis failed",
  "response_window.opened": "Response window opened",
  "response_window.reminder": "Response window reminder",
  "decision.recorded": "Decision recorded",
  "decision.refused": "Decision refused",
  "response_window.expired": "Response window expired",
  expiry_duplicate_ignored: "Duplicate expiry ignored",
  "scenario.selected": "Scenario selected",
  "scenario.no_match": "No scenario matched",
  "action.simulated": "Action simulated",
  "isolation.released": "Isolation released",
  "notification.sent": "Notification sent",
  "auth.login_succeeded": "Login succeeded",
  "auth.login_failed": "Login failed",
  "auth.logout": "Logout",
  "auth.lockout": "Account locked",
  "access.refused": "Access refused",
  "incident.created": "Incident created",
  "incident.updated": "Incident updated",
};

export const AUDIT_RESULT_LABELS: Record<AuditResult, string> = {
  success: "Success",
  failure: "Failure",
  refused: "Refused",
  ignored: "Ignored",
};

// Why C5 sent a notification (engine reasons; spec T03, T09, T11).
export const NOTIFICATION_REASON_LABELS: Record<string, string> = {
  freeze_started: "Response window opened, host isolated (SIMULATED)",
  no_match: "Window expired and no scenario matched: escalated",
  simulated_action_failed: "Simulated action failed: escalated",
};

// Risk factor names of C3's method (correlation-and-risk-design.md 9.3). C3's configuration has
// no labels (wireframes question 6), so these are C4 text; the raw name is shown on hover.
export const RISK_FACTOR_LABELS: Record<string, string> = {
  likelihood: "Evidence strength (L)",
  impact: "Points removed by the asset's impact (I)",
};

export const RISK_FLAG_LABELS: Record<RiskFlag, string> = {
  asset_unknown: "Asset not in the inventory: worst-case impact assumed",
  outcome_unknown: "Outcome not in the data: treated as succeeded",
  severity_default: "No severity in the data: default severity used",
};

export const LINK_KEY_LABELS: Record<LinkKey, string> = {
  host: "Same host",
  ip_pair: "Same source and destination IP",
  user: "Same user",
};

// Why C5's freeze gate opened no response window (backend/app/response/freeze.py).
export const NO_FREEZE_REASON_LABELS: Record<string, string> = {
  analysis_not_valid: "The analysis is not valid",
  risk_not_high: "Risk level is not High",
  confidence_below_threshold: "Confidence is below 0.75",
  window_already_open: "A response window is already open",
  no_target_host: "No host to isolate",
};

// Page names for the app shell: sidebar links and breadcrumbs (SOC UI phase 2). The sidebar link
// names are the accessible names the tests query; do not change them.
export const PAGE_LABELS = {
  overview: "Overview",
  incidents: "Incidents",
  review: "Review",
  entities: "Entities",
  upload: "Upload",
  configuration: "Configuration",
  notFound: "Page not found",
} as const;

// Incident sub-pages, the same names as the links on the incident detail page.
export const INCIDENT_SUBPAGE_LABELS = {
  report: "AI report",
  decision: "Pending decision",
  explanation: "Explanation",
  graph: "Entity graph",
  audit: "Audit trail",
} as const;

// The shell's SIMULATED strip (decision D5, wireframes section 2.4).
export const SIMULATED_BANNER_TEXT = "Responses in ICD are SIMULATED. No real system is changed.";
