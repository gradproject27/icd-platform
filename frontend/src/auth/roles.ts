import type { UserRole } from "../api/contracts";
import { ROLE_LABELS } from "../labels";

// Who sees what (auth-and-threat-model.md A3; decisions S8-D10, S8-D11, S8-D13). The dashboard
// only hides or explains with these. The server checks the decision role (FR-39); the reads
// behind the views do not check any role yet (gap: login, C5 T2-15).

/** Approve, reject, select and no_action: SOC Analyst only (D1.2). */
export const DECIDERS: readonly UserRole[] = ["soc_analyst"];

/** The Escalated group of the review queue: the analyst acts (T12, T16), the manager reviews (D7.2). */
export const ESCALATION_VIEWERS: readonly UserRole[] = ["soc_analyst", "soc_manager"];

/** "Review audit records" (A3, OD-24 proposal). "Own incidents only" for the analyst needs login. */
export const AUDIT_REVIEWERS: readonly UserRole[] = ["soc_analyst", "system_administrator"];

/** The configuration view: the two configuring roles of A3 (D7.5, OD-24 proposal). */
export const CONFIGURATION_VIEWERS: readonly UserRole[] = ["security_engineer", "system_administrator"];

/** "Run analysis again" on a failed or never-run analysis (C4-D3). */
export const ANALYSIS_RERUNNERS: readonly UserRole[] = ["security_engineer", "soc_analyst"];

/** "SOC Analyst and System Administrator", for messages. */
export const rolesText = (roles: readonly UserRole[]) => roles.map((role) => ROLE_LABELS[role]).join(" and ");
