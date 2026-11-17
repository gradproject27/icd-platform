import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import type { AnalysisReport, Incident } from "../api/contracts";
import { ApiError } from "../api/errors";
import { getIncidentEvents, getOriginalRecord, getReport } from "../api/incidents";
import type { IncidentEventItem, OriginalRecord } from "../api/proposed";
import { PageState } from "../components/PageState";
import { formatLocalDateTime } from "../countdown/clock";
import { IncidentHeader } from "../incidents/IncidentHeader";
import { RiskAndConfidence } from "../incidents/RiskAndConfidence";
import { STUB_BANNER } from "../incidents/format";
import { useIncident } from "../incidents/useIncident";

// Incident detail (wireframes.md 4.4): why the events were grouped and what sets the risk score.
// Everything is read from the API as stored: C3's correlation and risk, C1's events, the
// uploaded line for each event. Nothing is computed here.

const DECISION_STATES = new Set(["awaiting_human_decision", "escalated"]);

interface Detail {
  events: IncidentEventItem[];
  report: AnalysisReport | null;
}

async function loadDetail(incidentId: string, signal: AbortSignal): Promise<Detail> {
  const [events, report] = await Promise.all([
    getIncidentEvents(incidentId, signal),
    // The report only adds the risk justification here; a failed read must not hide the incident.
    getReport(incidentId, signal).catch(() => null),
  ]);
  return { events: events.items, report };
}

const dash = (value: string | null | undefined) => (value === null || value === undefined || value === "" ? "-" : value);

export function IncidentDetailPage() {
  const { incidentId = "" } = useParams();
  return <IncidentDetail key={incidentId} incidentId={incidentId} />;
}

function IncidentDetail({ incidentId }: { incidentId: string }) {
  const { load, retry } = useIncident(incidentId, (signal) => loadDetail(incidentId, signal));
  const { hash } = useLocation();
  const highlighted = hash.startsWith("#event-") ? decodeURIComponent(hash.slice("#event-".length)) : null;
  const back = <Link to="/incidents">Back to incidents</Link>;

  if (load.kind !== "ready") {
    return (
      <section>
        {back}
        <h1>Incident {incidentId}</h1>
        {load.kind === "loading" ? (
          <PageState kind="loading" message="Loading incident…" />
        ) : load.kind === "not_found" ? (
          <PageState kind="error" message={`Incident ${incidentId} was not found.`} />
        ) : (
          <PageState kind="error" message={load.message} onRetry={retry} />
        )}
      </section>
    );
  }

  const { summary, stub, extra } = load;
  const { incident } = summary;
  const encoded = encodeURIComponent(incidentId);

  return (
    <section>
      {back}
      <h1>Incident {incidentId}</h1>
      {stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}
      <IncidentHeader summary={summary} />
      <nav className="sub-nav" aria-label="Incident">
        <Link to={`/incidents/${encoded}/report`}>AI report</Link>
        {DECISION_STATES.has(incident.status ?? "new") && (
          <Link to={`/incidents/${encoded}/decision`}>Pending decision</Link>
        )}
        <Link to={`/incidents/${encoded}/audit`}>Audit trail</Link>
      </nav>

      <RiskAndConfidence incident={incident} confidence={incident.confidence} />
      <RiskBox incident={incident} justification={extra.report?.risk_justification ?? null} />
      <EventTimeline incidentId={incidentId} events={extra.events} highlighted={highlighted} onRetry={retry} />
    </section>
  );
}

function RiskBox({ incident, justification }: { incident: Incident; justification: string | null }) {
  const { risk } = incident;
  return (
    <section className="box" aria-labelledby="risk-heading">
      <h2 id="risk-heading">Risk</h2>
      {risk === null || risk === undefined ? (
        <p>Risk not scored yet. The risk engine computes it when the incident is created or updated.</p>
      ) : (
        <>
          <p>Score computed by the risk engine; justification written by the AI.</p>
          <table className="factor-table">
            <caption>Factors</caption>
            <thead>
              <tr>
                <th scope="col">Factor</th>
                <th scope="col">Value</th>
                <th scope="col">Weight</th>
                <th scope="col">Contribution</th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {risk.factors.map((factor) => (
                <tr key={factor.name}>
                  <th scope="row">{factor.name}</th>
                  <td>{factor.value.toFixed(2)}</td>
                  <td>{factor.weight.toFixed(2)}</td>
                  <td>{factor.contribution.toFixed(1)}</td>
                  <td>{dash(factor.reason)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {risk.top_contributors && risk.top_contributors.length > 0 && (
            <>
              <h3>Strongest evidence</h3>
              <ul>
                {risk.top_contributors.map((item) => (
                  <li key={item.event_id}>
                    {item.technique} ({item.event_id}): {item.reason}
                  </li>
                ))}
              </ul>
            </>
          )}
          {risk.flags && risk.flags.length > 0 && <p>Assumptions: {risk.flags.join(", ")}</p>}
          <p>Justification: {justification ?? "Not determined"}</p>
          <p className="muted">
            Configuration {risk.config_version}, computed{" "}
            <time dateTime={risk.computed_at}>{formatLocalDateTime(risk.computed_at)}</time>
          </p>
        </>
      )}
    </section>
  );
}

interface TimelineProps {
  incidentId: string;
  events: IncidentEventItem[];
  highlighted: string | null;
  onRetry: () => void;
}

/** Related events as a timeline, oldest first, each with its original record on request. */
function EventTimeline({ incidentId, events, highlighted, onRetry }: TimelineProps) {
  if (events.length === 0) {
    return (
      <section className="box" aria-labelledby="events-heading">
        <h2 id="events-heading">Related events (0)</h2>
        <PageState kind="error" message="No related events to show." onRetry={onRetry} />
      </section>
    );
  }
  const start = Date.parse(events[0]?.event.timestamp ?? "");
  return (
    <section className="box" aria-labelledby="events-heading">
      <h2 id="events-heading">Related events ({events.length})</h2>
      <p className="muted">Oldest first. Context events share an entity in the window and are never treated as flagged.</p>
      <ol className="timeline" aria-label="Event timeline">
        {events.map((item) => (
          <TimelineEvent
            key={item.event.event_id}
            incidentId={incidentId}
            item={item}
            offsetSeconds={(Date.parse(item.event.timestamp) - start) / 1000}
            highlighted={item.event.event_id === highlighted}
          />
        ))}
      </ol>
    </section>
  );
}

function offsetText(seconds: number): string {
  if (seconds <= 0) return "start";
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return minutes > 0 ? `+${minutes} min ${rest} s` : `+${rest} s`;
}

type Original = { kind: "closed" } | { kind: "loading" } | { kind: "error"; message: string } | { kind: "shown"; record: OriginalRecord };

function TimelineEvent({
  incidentId,
  item,
  offsetSeconds,
  highlighted,
}: {
  incidentId: string;
  item: IncidentEventItem;
  offsetSeconds: number;
  highlighted: boolean;
}) {
  const { event, role, link_keys } = item;
  const [original, setOriginal] = useState<Original>({ kind: "closed" });
  const label = event.label.attack_type ? `${event.label.status}, ${event.label.attack_type}` : event.label.status;

  const toggleOriginal = () => {
    if (original.kind === "shown" || original.kind === "error") {
      setOriginal({ kind: "closed" });
      return;
    }
    setOriginal({ kind: "loading" });
    getOriginalRecord(incidentId, event.event_id).then(
      (record) => setOriginal({ kind: "shown", record }),
      (error: unknown) =>
        setOriginal({
          kind: "error",
          message: error instanceof ApiError ? error.message : "Could not read the original record.",
        }),
    );
  };

  return (
    <li id={`event-${event.event_id}`} className={`timeline__item timeline__item--${role}${highlighted ? " timeline__item--highlighted" : ""}`}>
      <div className="timeline__when">
        {highlighted && <span aria-label="Cited event">&gt; </span>}
        <time dateTime={event.timestamp}>{formatLocalDateTime(event.timestamp).slice(11)}</time>{" "}
        <span className="muted">{offsetText(offsetSeconds)}</span>
      </div>
      <div className="timeline__body">
        <p>
          <strong className="role">{role === "flagged" ? "FLAGGED" : "context"}</strong> {event.event_id} ·{" "}
          {event.event_type} · Linked by {link_keys.length > 0 ? link_keys.join(", ") : "(first)"}
        </p>
        <p>{event.summary}</p>
        <dl className="event-fields">
          <div>
            <dt>Host</dt>
            <dd>{dash(event.host)}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{dash(event.src_ip)}</dd>
          </div>
          <div>
            <dt>Destination</dt>
            <dd>{dash(event.dst_ip)}</dd>
          </div>
          <div>
            <dt>User</dt>
            <dd>{dash(event.user)}</dd>
          </div>
          <div>
            <dt>Label</dt>
            <dd>{label}</dd>
          </div>
          <div>
            <dt>Record</dt>
            <dd>{event.provenance.record_ref}</dd>
          </div>
        </dl>
        <button type="button" className="link-button" onClick={toggleOriginal} aria-expanded={original.kind === "shown"}>
          {original.kind === "shown" ? "Hide original record" : "Show original record"}
        </button>
        {original.kind === "loading" && <p role="status">Reading the original record…</p>}
        {original.kind === "error" && <p role="alert">{original.message}</p>}
        {original.kind === "shown" && (
          <pre className="original-record" aria-label={`Original record ${original.record.record_ref}`}>
            {original.record.line}
          </pre>
        )}
      </div>
    </li>
  );
}
