import type { IncidentStatus } from "../api/contracts";
import { INCIDENT_STATUS_LABELS, SIMULATED_LABEL } from "../labels";

const SIMULATED_STATUSES = new Set<IncidentStatus>([
  "awaiting_human_decision",
  "response_in_progress",
  "escalated",
  "resolved",
]);

export function StatusChip({ status }: { status: IncidentStatus }) {
  return (
    <span className={`status-chip status-chip--${status}`}>
      <span className="status-chip__mark" aria-hidden="true" />
      <span>{INCIDENT_STATUS_LABELS[status]}</span>
      {SIMULATED_STATUSES.has(status) && <span className="simulated-badge">{SIMULATED_LABEL}</span>}
    </span>
  );
}
