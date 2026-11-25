import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "../api/errors";
import { getEntityRisk } from "../api/incidents";
import type { EntityRiskList } from "../api/proposed";
import { PageState } from "../components/PageState";
import { formatLocalDateTime } from "../countdown/clock";
import { RISK_LEVEL_LABELS } from "../labels";

// Entity risk (P3 of the competitor feature study): per source-side entity, a rank-weighted
// roll-up of its incidents' risk scores and the ATT&CK tactics of its flagged events, as the
// backend computes them (GET /entity-risk, entity_risk.toml). Read-only: it never changes an
// incident's score and never starts a response. Nothing is computed here.

type Load = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: EntityRiskList };

const FLAG_LABELS: Record<string, string> = {
  score_threshold: "Score threshold reached",
  tactic_threshold: "Tactic threshold reached",
};

export function EntityRiskPage() {
  const [params] = useSearchParams();
  const uploadId = params.get("upload_id") ?? undefined;
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getEntityRisk(uploadId, controller.signal).then(
      (data) => setLoad({ kind: "ready", data }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setLoad({ kind: "error", message: `Could not load the entity risk. ${reason}` });
      },
    );
    return () => controller.abort();
  }, [uploadId, attempt]);

  return (
    <section>
      <h1>Entity risk</h1>
      <p className="note">
        Each source-side entity (source IP, else user, else host of its flagged events) with a roll-up of its incidents'
        risk scores. A read-only view: it never changes an incident's score or level and never starts a response.
      </p>
      {load.kind === "loading" && <PageState kind="loading" message="Loading entity risk…" />}
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
      {load.kind === "ready" && <EntityTable data={load.data} />}
    </section>
  );
}

function EntityTable({ data }: { data: EntityRiskList }) {
  if (data.items.length === 0) {
    return <PageState kind="empty" message="No scored incident yet, so there is no entity to show." />;
  }
  return (
    <>
      <p className="muted">
        Window: {data.window_start ? formatLocalDateTime(data.window_start) : "-"} to{" "}
        {data.window_end ? formatLocalDateTime(data.window_end) : "-"} (dataset time). Flags at a score of{" "}
        {data.score_threshold} or more, or {data.tactics_threshold} or more ATT&CK tactics. Configuration{" "}
        {data.config_version}, tactics {data.tactics_config_version}.
      </p>
      <table className="factor-table">
        <caption>Entities, highest score first</caption>
        <thead>
          <tr>
            <th scope="col">Entity</th>
            <th scope="col">Score</th>
            <th scope="col">Level</th>
            <th scope="col">Incidents (score)</th>
            <th scope="col">ATT&CK tactics</th>
            <th scope="col">Flags</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => (
            <tr key={item.entity}>
              <th scope="row">{item.entity}</th>
              <td>{item.score} / 100</td>
              <td>{RISK_LEVEL_LABELS[item.level]}</td>
              <td>
                {item.incidents.map((incident, index) => (
                  <span key={incident.incident_id}>
                    {index > 0 && ", "}
                    <Link to={`/incidents/${encodeURIComponent(incident.incident_id)}`}>{incident.incident_id}</Link> (
                    {incident.score})
                  </span>
                ))}
              </td>
              <td>{item.tactics.length > 0 ? item.tactics.join(", ") : "-"}</td>
              <td>{item.flags.length > 0 ? item.flags.map((flag) => FLAG_LABELS[flag] ?? flag).join("; ") : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
