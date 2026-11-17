import type { AuditEventType, AuditRecord } from "../api/contracts";

// Groups for the audit view's filter (S8-D11), from response-workflow-spec.md section 11 and the
// auth doc. Typed on the generated enum, so a new event type is a compile error until grouped.

export type AuditGroup = "lifecycle" | "decisions" | "window" | "actions" | "notifications" | "access";

export const AUDIT_GROUP_LABELS: Record<AuditGroup, string> = {
  lifecycle: "Lifecycle",
  decisions: "Decisions",
  window: "Response window",
  actions: "Simulated actions",
  notifications: "Notifications",
  access: "Sign-in and access",
};

export const AUDIT_GROUP_OF: Record<AuditEventType, AuditGroup> = {
  status_changed: "lifecycle",
  transition_refused: "lifecycle",
  "analysis.failed": "lifecycle",
  "incident.created": "lifecycle",
  "incident.updated": "lifecycle",
  "decision.recorded": "decisions",
  "decision.refused": "decisions",
  "response_window.opened": "window",
  "response_window.reminder": "window",
  "response_window.expired": "window",
  expiry_duplicate_ignored: "window",
  "scenario.selected": "window",
  "scenario.no_match": "window",
  "action.simulated": "actions",
  "isolation.released": "actions",
  "notification.sent": "notifications",
  "auth.login_succeeded": "access",
  "auth.login_failed": "access",
  "auth.logout": "access",
  "auth.lockout": "access",
  "access.refused": "access",
};

/** "key: value" pairs of a record's details, in the order the server wrote them; null reads "-". */
export const detailPairs = (record: AuditRecord): [string, string][] =>
  Object.entries(record.details ?? {}).map(([key, value]) => [key, value === null || value === undefined || value === "" ? "-" : String(value)]);
