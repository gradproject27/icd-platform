import { useEffect, useState } from "react";
import { Link } from "react-router";
import type { ScenarioId } from "../api/contracts";
import { getRecentDecisions, getScenarios } from "../api/incidents";
import type { RecentDecisionList, ScenarioCatalogue } from "../api/proposed";
import { formatLocalDateTime } from "../countdown/clock";

// P6 of the competitor feature study: each simulated scenario's impact and how it is reverted
// (GET /scenarios, scenario_meta.toml), and the decisions of the last 72 hours from the audit trail
// (GET /decisions/recent). Display only: nothing here selects, approves or runs a scenario. Each
// part shows nothing when the server cannot answer, so it never hides the page it sits on.

const IMPACT_LABELS = { low: "Low", medium: "Medium", high: "High" } as const;
const DECISION_LABELS: Record<string, string> = {
  approve: "Approved",
  reject: "Rejected",
  select: "Selected another scenario",
  no_action: "No response needed",
  system_selection: "Selected by the system at the deadline",
};

function useScenarios(): ScenarioCatalogue | null {
  const [catalogue, setCatalogue] = useState<ScenarioCatalogue | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getScenarios(controller.signal).then(setCatalogue, () => undefined);
    return () => controller.abort();
  }, []);
  return catalogue;
}

/** One line under the recommendation: the scenario's impact and how it is reverted. */
export function ScenarioImpactLine({ scenarioId }: { scenarioId: ScenarioId }) {
  const item = useScenarios()?.items.find((scenario) => scenario.scenario_id === scenarioId);
  if (!item) return null;
  return (
    <p className="note">
      Impact: {IMPACT_LABELS[item.impact]}. {item.revert}
    </p>
  );
}

/** The catalogue's display metadata, for the configuration page. */
export function ScenarioMetaTable() {
  const catalogue = useScenarios();
  if (!catalogue) return null;
  return (
    <section className="box" aria-labelledby="config-scenario-meta">
      <h2 id="config-scenario-meta">Impact and revert of each scenario</h2>
      <p className="muted">
        Display only ({catalogue.meta_version}); the catalogue lookup never reads it. Catalogue {catalogue.config_version}.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Scenario</th>
            <th scope="col">Impact</th>
            <th scope="col">System may select</th>
            <th scope="col">How it is reverted</th>
          </tr>
        </thead>
        <tbody>
          {catalogue.items.map((item) => (
            <tr key={item.scenario_id}>
              <th scope="row">{item.scenario_id}</th>
              <td>{IMPACT_LABELS[item.impact]}</td>
              <td>{item.automatic ? "Yes" : "No, analyst only"}</td>
              <td>{item.revert}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** Decisions of the last 72 hours: who or what decided, newest first. */
export function RecentDecisions() {
  const [list, setList] = useState<RecentDecisionList | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getRecentDecisions(72, controller.signal).then(setList, () => undefined);
    return () => controller.abort();
  }, []);
  if (!list) return null;
  return (
    <section className="box" aria-labelledby="recent-decisions-heading">
      <h2 id="recent-decisions-heading">Decisions in the last {list.hours} hours</h2>
      {list.items.length === 0 ? (
        <p className="muted">No decision in the last {list.hours} hours.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Incident</th>
              <th scope="col">Decision</th>
              <th scope="col">Scenario</th>
              <th scope="col">By</th>
            </tr>
          </thead>
          <tbody>
            {list.items.map((item) => (
              <tr key={item.record_id}>
                <td>{formatLocalDateTime(item.occurred_at)}</td>
                <td>
                  <Link to={`/incidents/${encodeURIComponent(item.incident_id)}/audit`}>{item.incident_id}</Link>
                </td>
                <td>
                  {DECISION_LABELS[item.decision] ?? item.decision}
                  {item.comment ? ` ("${item.comment}")` : ""}
                </td>
                <td>{item.scenario_id ? `${item.scenario_id} (SIMULATED)` : "-"}</td>
                <td>{item.by === "system" ? "System" : item.actor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
