import { Link, useParams } from "react-router";

export function IncidentDetailPage() {
  const { incidentId } = useParams();

  return (
    <section>
      <h1>Incident {incidentId}</h1>
      <p>This page will show one incident: its related events and its deterministic risk score.</p>
      <nav className="sub-nav" aria-label="Incident">
        <Link to="report">AI report</Link>
        <Link to="decision">Pending decision</Link>
      </nav>
      <section className="placeholder">
        <h2>Related events</h2>
        <p>The events linked to this incident, flagged and context.</p>
      </section>
      <section className="placeholder">
        <h2>Risk score and justification</h2>
        <p>The score, its level and the per-factor breakdown, all computed by the backend.</p>
      </section>
    </section>
  );
}
