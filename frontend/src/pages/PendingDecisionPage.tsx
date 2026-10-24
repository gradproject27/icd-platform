import { Link, useParams } from "react-router";

// The three analyst options from docs/response-workflow-spec.md section 8. Every response is
// simulated and labelled SIMULATED (NFR-SF-01); the buttons stay disabled until the decision
// endpoint exists.
const OPTIONS = [
  "Approve recommended action (SIMULATED)",
  "Reject and release simulated isolation",
  "Select another scenario (S1 to S4, SIMULATED)",
];

export function PendingDecisionPage() {
  const { incidentId } = useParams();

  return (
    <section>
      <h1>Pending decision for incident {incidentId}</h1>
      <p>This page will let an analyst decide on the simulated response within the response window.</p>
      <Link to={`/incidents/${encodeURIComponent(incidentId ?? "")}`}>Back to incident</Link>
      <section className="placeholder">
        <h2>Countdown</h2>
        <p>Countdown (T1-11): the deadline comes from the server.</p>
      </section>
      <section className="placeholder">
        <h2>Recommended response (SIMULATED)</h2>
        <p>The scenario the system recommends. Nothing touches a real host.</p>
      </section>
      <div className="decision-options">
        {OPTIONS.map((label) => (
          <button type="button" key={label} disabled>
            {label}
          </button>
        ))}
      </div>
    </section>
  );
}
