import type { Incident } from "../api/contracts";
import type { IncidentEntities } from "../api/proposed";
import { formatLocalDateTime } from "../countdown/clock";
import { RISK_LEVEL_LABELS } from "../labels";

/** Shown above the list whenever the answer came from the dev-only stub server (X-ICD-Stub: 1). */
export const STUB_BANNER = "STUB DATA: scores and states are examples, not C3 results";

const ENTITIES_SHOWN = 3;

/** "YYYY-MM-DD HH:MM" in local time; lists drop the seconds (wireframes.md section 5). */
export const formatListTime = (iso: string) => formatLocalDateTime(iso).slice(0, 16);

/** "High 82" from C3's risk, or "Not scored". The level comes from C3; nothing is computed here. */
export const riskText = (incident: Incident) =>
  incident.risk ? `${RISK_LEVEL_LABELS[incident.risk.level]} ${incident.risk.score}` : "Not scored";

/** At most three entity values as text, groups split by " · ", then "+N"; the full list as a title. */
export function entitiesText(entities: IncidentEntities): { text: string; title: string } {
  const groups = [entities.hosts, entities.users, entities.ips];
  const total = groups.reduce((sum, group) => sum + group.length, 0);
  if (total === 0) return { text: "-", title: "No host, user or IP address" };

  let left = ENTITIES_SHOWN;
  const shown: string[] = [];
  for (const group of groups) {
    const taken = group.slice(0, left);
    left -= taken.length;
    if (taken.length > 0) shown.push(taken.join(", "));
  }
  const hidden = total - Math.min(total, ENTITIES_SHOWN);
  const title = [
    `Hosts: ${entities.hosts.join(", ") || "-"}`,
    `Users: ${entities.users.join(", ") || "-"}`,
    `IPs: ${entities.ips.join(", ") || "-"}`,
  ].join("; ");
  return { text: shown.join(" · ") + (hidden > 0 ? ` +${hidden}` : ""), title };
}
