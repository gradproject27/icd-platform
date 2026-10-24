import { Link } from "react-router";
import type { Incident } from "../api/contracts";
import { PageState } from "../components/PageState";
import { INCIDENT_STATUS_LABELS, RISK_LEVEL_LABELS } from "../labels";

// Empty until the incident endpoints exist (C3, Week 2). Typed with the generated contract so the
// table already compiles against the real Incident shape.
const incidents: Incident[] = [];

export function IncidentListPage() {
  return (
    <section>
      <h1>Incidents</h1>
      <p>This page will list correlated incidents with their risk level and lifecycle status.</p>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Incident ID</th>
            <th scope="col">Time</th>
            <th scope="col">Risk level</th>
            <th scope="col">Status</th>
            <th scope="col">Open</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr key={incident.incident_id}>
              <td>{incident.incident_id}</td>
              <td>
                <time dateTime={incident.first_event_at}>{incident.first_event_at}</time>
              </td>
              <td>{incident.risk ? RISK_LEVEL_LABELS[incident.risk.level] : "Not scored"}</td>
              <td>{INCIDENT_STATUS_LABELS[incident.status ?? "new"]}</td>
              <td>
                <Link to={`/incidents/${encodeURIComponent(incident.incident_id)}`}>Open</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {incidents.length === 0 && <PageState kind="empty" message="No incidents yet." />}
    </section>
  );
}
