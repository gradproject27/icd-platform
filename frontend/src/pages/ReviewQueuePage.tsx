import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/errors";
import { listIncidents } from "../api/incidents";
import type { IncidentSummary } from "../api/proposed";
import { DECIDERS, ESCALATION_VIEWERS, rolesText } from "../auth/roles";
import { useCurrentUser } from "../auth/useCurrentUser";
import { PageState } from "../components/PageState";
import { formatListTime, riskText, STUB_BANNER } from "../incidents/format";
import { reviewGroups, type ReviewGroup } from "../incidents/review";
import { SCENARIO_LABELS } from "../labels";
import { RecentDecisions } from "../incidents/ScenarioMeta";

// Review queue (S8-D10; response-workflow-spec.md section 5 and T04, T12, T16). Incidents that
// wait for an analyst with no timer: nothing runs on its own for them. The incidents and their
// risk, confidence and recommendation come from the API; incidents/review.ts groups them.

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: IncidentSummary[]; stub: boolean };

const confidenceText = (confidence: number | null | undefined) =>
  confidence === null || confidence === undefined ? "Not available" : `${Math.round(confidence * 100)}%`;

export function ReviewQueuePage() {
  const current = useCurrentUser();
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listIncidents(controller.signal).then(
      ({ data, stub }) => setLoad({ kind: "ready", items: data.items, stub }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setLoad({ kind: "error", message: `Could not load the review queue. ${reason}` });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const role = current.kind === "known" ? current.role : null;
  const canDecide = role !== null && DECIDERS.includes(role);
  const seesEscalated = role !== null && ESCALATION_VIEWERS.includes(role);

  return (
    <section>
      <h1>Review queue</h1>
      <p>Incidents waiting for an analyst with no response window. Oldest first.</p>

      {load.kind === "ready" && load.stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}
      {current.kind === "known" && !canDecide && (
        <p className="note" role="note">
          Read-only: only a SOC Analyst can decide.
        </p>
      )}

      {load.kind === "loading" && <PageState kind="loading" message="Loading the review queue…" />}
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
      {load.kind === "ready" && <Queue items={load.items} seesEscalated={seesEscalated} roleKnown={role !== null} />}
      <RecentDecisions />
    </section>
  );
}

function Queue({ items, seesEscalated, roleKnown }: { items: IncidentSummary[]; seesEscalated: boolean; roleKnown: boolean }) {
  const { groups, escalated, other } = reviewGroups(items);
  const waiting = groups.reduce((sum, group) => sum + group.items.length, 0);

  return (
    <>
      {waiting === 0 && (!seesEscalated || escalated.length === 0) && (
        <PageState kind="empty" message="Nothing waits for review." />
      )}
      {groups.map((group) => (
        <QueueGroup key={group.id} group={group} />
      ))}
      {seesEscalated ? (
        <QueueGroup
          group={{
            id: "escalated",
            title: "Escalated",
            note: "No scenario ran, or a simulated action failed. A SOC Analyst selects a scenario or marks it no response needed.",
            items: escalated,
          }}
        />
      ) : (
        <p className="muted">
          Escalated incidents are shown to the {rolesText(["soc_analyst", "soc_manager"])} only
          {roleKnown ? "." : ". The API did not say who you are."}
        </p>
      )}
      {other > 0 && (
        <p className="muted">
          {other} more {other === 1 ? "incident awaits" : "incidents await"} a decision with a High risk at confidence 0.75 or
          more, or with no score. <Link to="/incidents?state=awaiting_human_decision">Open them in the incident list</Link>.
        </p>
      )}
    </>
  );
}

function QueueGroup({ group }: { group: ReviewGroup }) {
  const headingId = `review-${group.id}`;
  return (
    <section className="box" aria-labelledby={headingId}>
      <h2 id={headingId}>
        {group.title} ({group.items.length})
      </h2>
      <p className="muted">{group.note}</p>
      {group.items.length === 0 ? (
        <p>None.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Incident ID</th>
              <th scope="col">First event</th>
              <th scope="col">Type</th>
              <th scope="col">Risk</th>
              <th scope="col">Confidence</th>
              <th scope="col">Recommended (advice)</th>
              <th scope="col">Review</th>
            </tr>
          </thead>
          <tbody>
            {group.items.map((summary) => (
              <QueueRow key={summary.incident.incident_id} summary={summary} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function QueueRow({ summary }: { summary: IncidentSummary }) {
  const { incident, recommended_scenario_id: recommended } = summary;
  const id = encodeURIComponent(incident.incident_id);
  return (
    <tr>
      <td>
        <Link to={`/incidents/${id}`}>{incident.incident_id}</Link>
      </td>
      <td>
        <time dateTime={incident.first_event_at}>{formatListTime(incident.first_event_at)}</time>
      </td>
      <td>{incident.incident_type ?? "Not classified"}</td>
      <td>{riskText(incident)}</td>
      <td>{confidenceText(incident.confidence)}</td>
      <td title={recommended ? SCENARIO_LABELS[recommended] : undefined}>
        {recommended ? `${recommended} (SIMULATED)` : "No matching scenario"}
      </td>
      <td>
        <Link to={`/incidents/${id}/decision`} aria-label={`Review ${incident.incident_id}`}>
          Review
        </Link>
      </td>
    </tr>
  );
}
