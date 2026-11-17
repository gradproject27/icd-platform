import { Link, useParams } from "react-router";
import { getIncidentEvents } from "../api/incidents";
import { PageState } from "../components/PageState";
import { STUB_BANNER } from "../incidents/format";
import { buildGraph, GRAPH_MAX_EVENTS, type EntityGraph } from "../incidents/graph";
import { IncidentHeader } from "../incidents/IncidentHeader";
import { useIncident } from "../incidents/useIncident";
import { LINK_KEY_LABELS } from "../labels";

// Entity graph (S8-D14, optional view), in plain SVG with no graph library. Events in time order
// on the left, the hosts, users and IPs they name on the right. A solid line is a correlation link
// (the field is one of the event's link_keys); a dashed line is a field the event only mentions.
// Flagged and context differ in text, not colour alone. The same edges are listed in a table.

const WIDTH = 720;
const ROW = 34;
const TOP = 20;
const EVENT_X = 10;
const ENTITY_X = 470;
const NODE_W = 240;
const NODE_H = 24;

const FIELD_LABELS = { host: "host", user: "user", src_ip: "source IP", dst_ip: "destination IP" } as const;

export function EntityGraphPage() {
  const { incidentId = "" } = useParams();
  return <GraphView key={incidentId} incidentId={incidentId} />;
}

function GraphView({ incidentId }: { incidentId: string }) {
  const { load, retry } = useIncident(incidentId, (signal) => getIncidentEvents(incidentId, signal));
  const back = <Link to={`/incidents/${encodeURIComponent(incidentId)}`}>Back to incident</Link>;

  if (load.kind !== "ready") {
    return (
      <section>
        {back}
        <h1>Entity graph of incident {incidentId}</h1>
        {load.kind === "loading" ? (
          <PageState kind="loading" message="Loading the events…" />
        ) : load.kind === "not_found" ? (
          <PageState kind="error" message={`Incident ${incidentId} was not found.`} />
        ) : (
          <PageState kind="error" message={load.message} onRetry={retry} />
        )}
      </section>
    );
  }

  const graph = buildGraph(load.extra.items);
  return (
    <section>
      {back}
      <h1>Entity graph of incident {incidentId}</h1>
      {load.stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}
      <IncidentHeader summary={load.summary} />
      {graph.events.length === 0 ? (
        <PageState kind="error" message="No related events to show." onRetry={retry} />
      ) : (
        <>
          <p className="muted">
            Solid line: the event was grouped through this value (its link key). Dashed line: the event only names it.
          </p>
          {graph.total > graph.events.length && (
            <p className="note" role="note">
              Showing the first {GRAPH_MAX_EVENTS} of {graph.total} events.
            </p>
          )}
          <GraphSvg graph={graph} />
          <EdgeTable graph={graph} />
        </>
      )}
    </section>
  );
}

function GraphSvg({ graph }: { graph: EntityGraph }) {
  const eventY = new Map(graph.events.map((item, index) => [item.event.event_id, TOP + index * ROW]));
  const entityY = new Map(graph.entities.map((entity, index) => [entity.id, TOP + index * ROW]));
  const height = TOP * 2 + Math.max(graph.events.length, graph.entities.length) * ROW;
  const middle = NODE_H / 2;

  return (
    <div className="graph">
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        role="img"
        aria-label={`Entity graph: ${graph.events.length} events and ${graph.entities.length} hosts, users and IPs. The table below lists every line.`}
      >
        {graph.edges.map((edge) => (
          <line
            key={`${edge.eventId}-${edge.field}`}
            className={`graph__edge${edge.linkedBy ? " graph__edge--linked" : ""}`}
            x1={EVENT_X + NODE_W}
            y1={(eventY.get(edge.eventId) ?? 0) + middle}
            x2={ENTITY_X}
            y2={(entityY.get(edge.entityId) ?? 0) + middle}
          />
        ))}
        {graph.events.map((item) => (
          <g key={item.event.event_id} className={`graph__node graph__node--${item.role}`}>
            <rect x={EVENT_X} y={eventY.get(item.event.event_id)} width={NODE_W} height={NODE_H} rx={3} />
            <text x={EVENT_X + 8} y={(eventY.get(item.event.event_id) ?? 0) + 16}>
              {item.role === "flagged" ? "FLAGGED" : "context"} {item.event.event_id}
            </text>
          </g>
        ))}
        {graph.entities.map((entity) => (
          <g key={entity.id} className="graph__node graph__node--entity">
            <rect x={ENTITY_X} y={entityY.get(entity.id)} width={NODE_W} height={NODE_H} rx={3} />
            <text x={ENTITY_X + 8} y={(entityY.get(entity.id) ?? 0) + 16}>
              {entity.kind} {entity.value}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function EdgeTable({ graph }: { graph: EntityGraph }) {
  const roleOf = new Map(graph.events.map((item) => [item.event.event_id, item.role]));
  const valueOf = new Map(graph.entities.map((entity) => [entity.id, entity.value]));
  return (
    <table className="table">
      <caption>Every line of the graph</caption>
      <thead>
        <tr>
          <th scope="col">Event</th>
          <th scope="col">Field</th>
          <th scope="col">Value</th>
          <th scope="col">Grouped through it</th>
        </tr>
      </thead>
      <tbody>
        {graph.edges.map((edge) => (
          <tr key={`${edge.eventId}-${edge.field}`}>
            <td>
              {roleOf.get(edge.eventId) === "flagged" ? "FLAGGED" : "context"} {edge.eventId}
            </td>
            <td>{FIELD_LABELS[edge.field]}</td>
            <td>{valueOf.get(edge.entityId)}</td>
            <td>{edge.linkedBy ? `Yes: ${LINK_KEY_LABELS[edge.linkedBy]}` : "No"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
