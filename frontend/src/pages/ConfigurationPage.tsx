import { useEffect, useState } from "react";
import type { ScenarioId } from "../api/contracts";
import { ApiError } from "../api/errors";
import { listIncidents } from "../api/incidents";
import type { IncidentSummary } from "../api/proposed";
import { CONFIGURATION_VIEWERS } from "../auth/roles";
import { useCurrentUser } from "../auth/useCurrentUser";
import { PageState } from "../components/PageState";
import { RoleGate } from "../components/RoleGate";
import { STUB_BANNER } from "../incidents/format";
import { SCENARIO_LABELS } from "../labels";

// Configuration, read-only (S8-D13). The API serves no configuration yet (gap: GET /config/risk,
// C3), so this page shows only what the incidents carry: which risk and correlation configuration
// versions scored and grouped them (AS-04). It never shows thresholds or weights as literals.
// The fixed window and the catalogue are the response spec's (OD-17, OD-20). A3: Security
// Engineer and System Administrator.

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: IncidentSummary[]; stub: boolean };

const SCENARIOS = Object.keys(SCENARIO_LABELS) as ScenarioId[];

/** Incidents per version, most used first; `missing` names incidents without one. */
function versionCounts(values: (string | null | undefined)[], missing: string): [string, number][] {
  const counts = new Map<string, number>();
  for (const value of values) {
    const key = value ?? missing;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function ConfigurationPage() {
  const current = useCurrentUser();
  return (
    <section>
      <h1>Configuration</h1>
      <p>Read-only. What configured the risk scores, the grouping and the simulated responses.</p>
      <RoleGate current={current} allowed={CONFIGURATION_VIEWERS} what="the configuration">
        <Configuration />
      </RoleGate>
    </section>
  );
}

function Configuration() {
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listIncidents(controller.signal).then(
      ({ data, stub }) => setLoad({ kind: "ready", items: data.items, stub }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setLoad({ kind: "error", message: `Could not load the configuration versions. ${reason}` });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  return (
    <>
      <section className="box" aria-labelledby="config-versions">
        <h2 id="config-versions">Versions in use</h2>
        {load.kind === "loading" && <PageState kind="loading" message="Loading the configuration versions…" />}
        {load.kind === "error" && (
          <PageState
            kind="error"
            message={load.message}
            onRetry={() => {
              setLoad({ kind: "loading" });
              setAttempt((value) => value + 1);
            }}
          />
        )}
        {load.kind === "ready" && load.stub && (
          <p className="stub-banner" role="note">
            {STUB_BANNER}
          </p>
        )}
        {load.kind === "ready" && load.items.length === 0 && (
          <PageState kind="empty" message="No incidents yet, so no configuration version is in use." />
        )}
        {load.kind === "ready" && load.items.length > 0 && (
          <>
            <p className="muted">From the {load.items.length} stored incidents. Every value change creates a new version.</p>
            <VersionTable
              caption="Risk configuration (C3, risk.toml)"
              rows={versionCounts(
                load.items.map(({ incident }) => incident.risk?.config_version),
                "Not scored",
              )}
            />
            <VersionTable
              caption="Correlation configuration (C3, correlation.toml)"
              rows={versionCounts(
                load.items.map(({ incident }) => incident.correlation_config_version),
                "Not recorded",
              )}
            />
          </>
        )}
        <p className="note">
          Thresholds, weights and the other configured values are not served by the API yet (gap for C3: a read-only
          configuration endpoint).
        </p>
      </section>

      <section className="box" aria-labelledby="config-window">
        <h2 id="config-window">Response window</h2>
        <p>60 seconds, fixed by the server. No role can change it in the MVP (OD-17).</p>
      </section>

      <section className="box" aria-labelledby="config-catalogue">
        <h2 id="config-catalogue">
          Response catalogue v0 <span className="simulated-badge">[SIMULATED]</span>
        </h2>
        <p className="muted">Every scenario is a simulation. S4 is never selected automatically (OD-20).</p>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Scenario</th>
              <th scope="col">Simulated behaviour</th>
            </tr>
          </thead>
          <tbody>
            {SCENARIOS.map((id) => (
              <tr key={id}>
                <th scope="row">{id}</th>
                <td>{SCENARIO_LABELS[id]} (SIMULATED)</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function VersionTable({ caption, rows }: { caption: string; rows: [string, number][] }) {
  return (
    <table className="table">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Version</th>
          <th scope="col">Incidents</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([version, count]) => (
          <tr key={version}>
            <th scope="row">{version}</th>
            <td>{count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
