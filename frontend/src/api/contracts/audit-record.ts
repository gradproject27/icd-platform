/* GENERATED from contracts/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * The four roles (D7.1).
 *
 * This interface was referenced by `AuditRecord`'s JSON-Schema
 * via the `definition` "UserRole".
 */
export type UserRole = "soc_analyst" | "soc_manager" | "security_engineer" | "system_administrator";
/**
 * Audit event types (response spec section 11, auth doc; incident.* proposed by C3).
 *
 * This interface was referenced by `AuditRecord`'s JSON-Schema
 * via the `definition` "AuditEventType".
 */
export type AuditEventType =
  | "status_changed"
  | "transition_refused"
  | "analysis.failed"
  | "response_window.opened"
  | "response_window.reminder"
  | "decision.recorded"
  | "decision.refused"
  | "response_window.expired"
  | "expiry_duplicate_ignored"
  | "scenario.selected"
  | "scenario.no_match"
  | "action.simulated"
  | "isolation.released"
  | "notification.sent"
  | "auth.login_succeeded"
  | "auth.login_failed"
  | "auth.logout"
  | "auth.lockout"
  | "access.refused"
  | "incident.created"
  | "incident.updated";
/**
 * Outcome of the audited operation.
 *
 * This interface was referenced by `AuditRecord`'s JSON-Schema
 * via the `definition` "AuditResult".
 */
export type AuditResult = "success" | "failure" | "refused" | "ignored";

/**
 * A record of a security-relevant decision or action (FR-35, C-14, NFR-SF-07).
 */
export interface AuditRecord {
  /**
   * User ID, system, or anonymous for a failed login with no known user.
   */
  actor: string;
  /**
   * Role of the user; null for system and anonymous.
   */
  actor_role?: UserRole | null;
  /**
   * For example previous and new state, scenario ID, window ID, reason. Never passwords, hashes or session tokens.
   */
  details?: {
    [k: string]: string | number | boolean | null | undefined;
  };
  event_type: AuditEventType;
  /**
   * Incident ID; null for records with no incident, such as login.
   */
  incident_id?: string | null;
  /**
   * Database time (now()) when written, UTC.
   */
  occurred_at: string;
  /**
   * Unique record ID.
   */
  record_id: string;
  result: AuditResult;
  /**
   * Contract version.
   */
  schema_version?: "1.0";
  /**
   * True exactly for action.simulated and isolation.released (NFR-SF-07).
   */
  simulated?: boolean;
}
