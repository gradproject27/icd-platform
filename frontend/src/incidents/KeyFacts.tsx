import { Link } from "react-router";
import type { IncidentKeyFacts, KeyFactItem } from "../api/proposed";
import { formatLocalDateTime } from "../countdown/clock";

// Key facts (P1 of the competitor feature study, PR #51): start, assets and indicators that the
// backend computes by code from the incident's flagged events (GET /incidents/{id}/key-facts).
// They are not AI output and never sent to the model. Nothing is computed here.

type ListKey = "attack_types" | "tactics" | "hosts" | "internal_ips" | "external_ips" | "destination_ports" | "accounts";

const ROWS: { key: keyof Pick<IncidentKeyFacts, ListKey>; title: string }[] = [
  { key: "attack_types", title: "Attack types (dataset labels)" },
  { key: "tactics", title: "MITRE ATT&CK tactics (from the table, not the AI)" },
  { key: "hosts", title: "Hosts" },
  { key: "internal_ips", title: "Internal IPs" },
  { key: "external_ips", title: "External IPs" },
  { key: "destination_ports", title: "Destination ports" },
  { key: "accounts", title: "Accounts" },
];

function EventLinks({ incidentId, item }: { incidentId: string; item: KeyFactItem }) {
  const encoded = encodeURIComponent(incidentId);
  return (
    <span className="muted">
      {" ("}
      {item.event_ids.map((id, index) => (
        <span key={id}>
          {index > 0 && ", "}
          <Link to={`/incidents/${encoded}#event-${encodeURIComponent(id)}`}>{id}</Link>
        </span>
      ))}
      {item.event_count > item.event_ids.length && ", …"})
    </span>
  );
}

function Values({ incidentId, items }: { incidentId: string; items: KeyFactItem[] }) {
  if (items.length === 0) return <span className="muted">None</span>;
  return (
    <ul className="key-facts__values">
      {items.map((item) => (
        <li key={item.value}>
          <strong>{item.value}</strong> × {item.event_count}
          <EventLinks incidentId={incidentId} item={item} />
        </li>
      ))}
    </ul>
  );
}

/** The key facts box; `facts` null means the server did not answer them (old API or stub). */
export function KeyFacts({ incidentId, facts }: { incidentId: string; facts: IncidentKeyFacts | null }) {
  if (facts === null) {
    return (
      <section className="box" aria-labelledby="key-facts-heading">
        <h2 id="key-facts-heading">Key facts</h2>
        <p className="muted">Key facts are not available from this server.</p>
      </section>
    );
  }
  const plural = facts.flagged_event_count === 1 ? "" : "s";
  return (
    <section className="box" aria-labelledby="key-facts-heading">
      <h2 id="key-facts-heading">Key facts</h2>
      <p className="note">
        Computed by code from the {facts.flagged_event_count} flagged event{plural}, not by the AI. The{" "}
        {facts.context_event_count} context event{facts.context_event_count === 1 ? " is" : "s are"} not counted.
        Internal and external addresses follow the response configuration {facts.network_config_version}.
      </p>
      <dl className="event-fields">
        <div>
          <dt>Started</dt>
          <dd>
            {formatLocalDateTime(facts.started_at)} ({facts.first_flagged_event_id})
          </dd>
        </div>
        <div>
          <dt>Started on</dt>
          <dd>{facts.started_on ?? "-"}</dd>
        </div>
        <div>
          <dt>From (external source)</dt>
          <dd>{facts.origin_ip ?? "-"}</dd>
        </div>
        <div>
          <dt>Last flagged event</dt>
          <dd>
            {formatLocalDateTime(facts.last_flagged_at)} ({facts.last_flagged_event_id})
          </dd>
        </div>
      </dl>
      <table className="factor-table">
        <caption>What the flagged events name (count, cited events)</caption>
        <tbody>
          {ROWS.map(({ key, title }) => (
            <tr key={key}>
              <th scope="row">{title}</th>
              <td>
                <Values incidentId={incidentId} items={facts[key]} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {facts.truncated && <p className="muted">Some lists are cut at 20 values.</p>}
      <h3>Patterns ({facts.patterns_config_version})</h3>
      {facts.patterns.length === 0 ? (
        <p className="muted">No count or order pattern among the flagged events.</p>
      ) : (
        <ul className="key-facts__values" aria-label="Patterns">
          {facts.patterns.map((pattern) => (
            <li key={`${pattern.pattern_id}|${pattern.key}`}>
              <strong>{pattern.title}</strong> ({pattern.key}):{" "}
              {pattern.event_ids.map((id, index) => (
                <span key={id}>
                  {index > 0 && " → "}
                  <Link to={`/incidents/${encodeURIComponent(incidentId)}#event-${encodeURIComponent(id)}`}>{id}</Link>
                </span>
              ))}
            </li>
          ))}
        </ul>
      )}
      <p className="muted">Patterns are markers over the flagged events only: they never flag an event or change a score.</p>
      <p className="muted">
        Tactics come from the reviewed table {facts.tactics_config_version} through each event's dataset attack type.
        MITRE ATT&CK® © The MITRE Corporation, used under its terms of use.
      </p>
    </section>
  );
}
