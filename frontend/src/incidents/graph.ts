import type { LinkKey } from "../api/contracts";
import type { IncidentEventItem } from "../api/proposed";

// The entity graph's data (S8-D14): which event names which host, user or IP. It only regroups
// the events the API sent; whether an edge is a correlation link comes from the event's link_keys.

/** Most events drawn; the graph stops being readable above this. */
export const GRAPH_MAX_EVENTS = 50;

export type EntityKind = "host" | "user" | "ip";
export type EventField = "host" | "user" | "src_ip" | "dst_ip";

export interface GraphEntity {
  id: string;
  kind: EntityKind;
  value: string;
}

export interface GraphEdge {
  eventId: string;
  entityId: string;
  field: EventField;
  /** The link key that grouped the event through this field, or null when it is not one. */
  linkedBy: LinkKey | null;
}

export interface EntityGraph {
  events: IncidentEventItem[];
  /** Events in the incident, including those not drawn. */
  total: number;
  entities: GraphEntity[];
  edges: GraphEdge[];
}

const FIELDS: { field: EventField; kind: EntityKind; key: LinkKey }[] = [
  { field: "host", kind: "host", key: "host" },
  { field: "user", kind: "user", key: "user" },
  { field: "src_ip", kind: "ip", key: "ip_pair" },
  { field: "dst_ip", kind: "ip", key: "ip_pair" },
];

const KIND_ORDER: Record<EntityKind, number> = { host: 0, user: 1, ip: 2 };

export function buildGraph(items: IncidentEventItem[], max = GRAPH_MAX_EVENTS): EntityGraph {
  const events = items.slice(0, max);
  const entities = new Map<string, GraphEntity>();
  const edges: GraphEdge[] = [];
  for (const item of events) {
    for (const { field, kind, key } of FIELDS) {
      const value = item.event[field];
      if (value === null || value === undefined || value === "") continue;
      const id = `${kind}:${value}`;
      if (!entities.has(id)) entities.set(id, { id, kind, value });
      edges.push({ eventId: item.event.event_id, entityId: id, field, linkedBy: item.link_keys.includes(key) ? key : null });
    }
  }
  const sorted = [...entities.values()].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || a.value.localeCompare(b.value));
  return { events, total: items.length, entities: sorted, edges };
}
