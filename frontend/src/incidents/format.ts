import type { IncidentEntities } from "../api/proposed";

/** Shown above the list whenever the answer came from the dev-only stub server (X-ICD-Stub: 1). */
export const STUB_BANNER = "STUB DATA: scores and states are examples, not C3 results";

const ENTITIES_SHOWN = 3;

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
