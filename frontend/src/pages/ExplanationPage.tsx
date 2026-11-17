import { Link, useParams } from "react-router";
import type { AnalysisReport, AuditRecord, Incident, LinkKey, RiskAssessment, ScenarioId } from "../api/contracts";
import { getAuditTrail, getIncidentEvents, getReport } from "../api/incidents";
import type { IncidentEventItem } from "../api/proposed";
import { PageState } from "../components/PageState";
import { formatLocalDateTime } from "../countdown/clock";
import { STUB_BANNER } from "../incidents/format";
import { IncidentHeader } from "../incidents/IncidentHeader";
import { useIncident } from "../incidents/useIncident";
import {
  LINK_KEY_LABELS,
  NO_FREEZE_REASON_LABELS,
  RISK_FACTOR_LABELS,
  RISK_FLAG_LABELS,
  RISK_LEVEL_LABELS,
  SCENARIO_LABELS,
} from "../labels";

// Explanation (S8-D12; wireframes 4.4, NFR-SF-05, C-17): why this risk score, why these events
// were grouped, and why there is or is not a response window. Every value is the API's: C3's
// stored risk and correlation, C1's events, C5's freeze-gate record in the audit trail, and the
// AI report's justification when one is stored. Nothing is computed here, only counted and labelled.

interface Explanation {
  events: IncidentEventItem[];
  /** null when the audit trail could not be read: only the third section needs it. */
  audit: AuditRecord[] | null;
  report: AnalysisReport | null;
}

async function loadExplanation(incidentId: string, signal: AbortSignal): Promise<Explanation> {
  const [events, audit, report] = await Promise.all([
    getIncidentEvents(incidentId, signal),
    getAuditTrail(incidentId, signal).catch(() => null),
    getReport(incidentId, signal).catch(() => null),
  ]);
  return { events: events.items, audit, report };
}

const LINK_KEYS = Object.keys(LINK_KEY_LABELS) as LinkKey[];

const points = (value: number) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(1)}`;

export function ExplanationPage() {
  const { incidentId = "" } = useParams();
  return <ExplanationView key={incidentId} incidentId={incidentId} />;
}

function ExplanationView({ incidentId }: { incidentId: string }) {
  const { load, retry } = useIncident(incidentId, (signal) => loadExplanation(incidentId, signal));
  const back = <Link to={`/incidents/${encodeURIComponent(incidentId)}`}>Back to incident</Link>;

  if (load.kind !== "ready") {
    return (
      <section>
        {back}
        <h1>Explanation of incident {incidentId}</h1>
        {load.kind === "loading" ? (
          <PageState kind="loading" message="Loading the explanation…" />
        ) : load.kind === "not_found" ? (
          <PageState kind="error" message={`Incident ${incidentId} was not found.`} />
        ) : (
          <PageState kind="error" message={load.message} onRetry={retry} />
        )}
      </section>
    );
  }

  const { summary, stub, extra } = load;
  return (
    <section>
      {back}
      <h1>Explanation of incident {incidentId}</h1>
      {stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}
      <IncidentHeader summary={summary} />
      <RiskExplanation incident={summary.incident} report={extra.report} />
      <GroupingExplanation incident={summary.incident} events={extra.events} />
      <WindowExplanation audit={extra.audit} />
    </section>
  );
}

function RiskExplanation({ incident, report }: { incident: Incident; report: AnalysisReport | null }) {
  const { risk } = incident;
  return (
    <section className="box" aria-labelledby="why-score">
      <h2 id="why-score">Why this risk score</h2>
      {risk === null || risk === undefined ? (
        <p>Risk not scored yet. The risk engine computes it when the incident is created or updated.</p>
      ) : (
        <ScoreParts incidentId={incident.incident_id} risk={risk} />
      )}
      <p>
        Justification (written by the AI):{" "}
        {report ? (report.risk_justification ?? "Not determined") : "Not determined: no AI report is stored yet."}
      </p>
    </section>
  );
}

function ScoreParts({ incidentId, risk }: { incidentId: string; risk: RiskAssessment }) {
  const flags = risk.flags ?? [];
  const contributors = risk.top_contributors ?? [];
  return (
    <>
      <p>
        <strong>
          {RISK_LEVEL_LABELS[risk.level]} {risk.score} / 100
        </strong>
        , computed by the risk engine (C3) from configured values, never by the AI.
      </p>
      <table className="factor-table">
        <caption>What sets the score</caption>
        <thead>
          <tr>
            <th scope="col">Factor</th>
            <th scope="col">Value</th>
            <th scope="col">Points</th>
            <th scope="col">Reason</th>
          </tr>
        </thead>
        <tbody>
          {risk.factors.map((factor) => (
            <tr key={factor.name}>
              <th scope="row" title={factor.name}>
                {RISK_FACTOR_LABELS[factor.name] ?? factor.name}
              </th>
              <td>{factor.value.toFixed(2)}</td>
              <td>{points(factor.contribution)}</td>
              <td>{factor.reason ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Assumptions</h3>
      {flags.length === 0 ? (
        <p>None: the data had every value the score needs.</p>
      ) : (
        <ul>
          {flags.map((flag) => (
            <li key={flag} title={flag}>
              {RISK_FLAG_LABELS[flag]}
            </li>
          ))}
        </ul>
      )}

      {contributors.length > 0 && (
        <>
          <h3>Strongest evidence</h3>
          <ol>
            {contributors.map((item) => (
              <li key={item.event_id}>
                {item.technique} from {item.entity}, strength {item.strength.toFixed(2)}:{" "}
                <Link to={`/incidents/${encodeURIComponent(incidentId)}#event-${encodeURIComponent(item.event_id)}`}>
                  {item.event_id}
                </Link>
                . {item.reason}
              </li>
            ))}
          </ol>
        </>
      )}

      <p className="muted">
        Risk configuration {risk.config_version}, computed{" "}
        <time dateTime={risk.computed_at} title={risk.computed_at}>
          {formatLocalDateTime(risk.computed_at)}
        </time>
      </p>
    </>
  );
}

function GroupingExplanation({ incident, events }: { incident: Incident; events: IncidentEventItem[] }) {
  const flagged = events.filter((item) => item.role === "flagged").length;
  const first = events.find((item) => item.link_keys.length === 0);
  const byKey = LINK_KEYS.map((key) => ({ key, count: events.filter((item) => item.link_keys.includes(key)).length }));
  const { split } = incident;
  return (
    <section className="box" aria-labelledby="why-grouped">
      <h2 id="why-grouped">Why these events are grouped</h2>
      {events.length === 0 ? (
        <p>The events of this incident could not be read.</p>
      ) : (
        <>
          <p>
            {events.length} events: {flagged} flagged by the dataset label, {events.length - flagged} context. Context events
            share an entity in the time window and are never treated as flagged.
          </p>
          {first && (
            <p>
              Started by{" "}
              <Link to={`/incidents/${encodeURIComponent(incident.incident_id)}#event-${encodeURIComponent(first.event.event_id)}`}>
                {first.event.event_id}
              </Link>
              .
            </p>
          )}
          <table className="table">
            <caption>Events linked by each key</caption>
            <thead>
              <tr>
                <th scope="col">Key</th>
                <th scope="col">Events</th>
              </tr>
            </thead>
            <tbody>
              {byKey.map(({ key, count }) => (
                <tr key={key}>
                  <th scope="row" title={key}>
                    {LINK_KEY_LABELS[key]}
                  </th>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {split && (
        <p>
          Part {split.part} of {split.parts}: the group was cut at the size cap of {split.cap} linked events (group{" "}
          {split.group_id}).
        </p>
      )}
      <p className="muted">Correlation configuration {incident.correlation_config_version ?? "not recorded"}</p>
    </section>
  );
}

/** The latest freeze-gate record C5 wrote when the analysis was recorded (T03, T04). */
function gateRecord(audit: AuditRecord[]): AuditRecord | null {
  const gates = audit.filter((record) => record.event_type === "status_changed" && typeof record.details?.freeze === "boolean");
  return gates[gates.length - 1] ?? null;
}

function WindowExplanation({ audit }: { audit: AuditRecord[] | null }) {
  const gate = audit ? gateRecord(audit) : null;
  const details = gate?.details ?? {};
  const reasons = typeof details.reasons === "string" ? details.reasons.split(",").filter(Boolean) : [];
  const recommended = typeof details.recommended_scenario_id === "string" ? (details.recommended_scenario_id as ScenarioId) : null;
  const level = typeof details.risk_level === "string" ? details.risk_level : null;
  const confidence = typeof details.confidence === "number" ? `${Math.round(details.confidence * 100)}%` : "not available";

  return (
    <section className="box" aria-labelledby="why-window">
      <h2 id="why-window">Why there is or is not a response window</h2>
      {audit === null ? (
        <p>Could not read the audit trail, where the response engine records this.</p>
      ) : gate === null ? (
        <p>Not analysed yet. The response engine records this when the analysis of the incident is recorded.</p>
      ) : (
        <>
          {details.freeze === true ? (
            <p>
              A 60-second response window was opened: the analysis is valid, the risk is High, the confidence is 0.75 or more,
              and no window was open.
            </p>
          ) : (
            <>
              <p>No response window was opened, and no automatic action runs, because:</p>
              <ul>
                {reasons.map((reason) => (
                  <li key={reason} title={reason}>
                    {NO_FREEZE_REASON_LABELS[reason] ?? reason}
                  </li>
                ))}
              </ul>
            </>
          )}
          <p>
            Checked when the analysis was recorded: risk level {level ? (RISK_LEVEL_LABELS[level as keyof typeof RISK_LEVEL_LABELS] ?? level) : "not scored"},
            confidence {confidence}.
          </p>
          <p>
            Recommended response:{" "}
            {recommended ? (
              <>
                {recommended} {SCENARIO_LABELS[recommended]} <span className="simulated-badge">[SIMULATED]</span>. Advice from the
                catalogue lookup, not chosen by the AI and not run until an analyst or the window expiry decides.
              </>
            ) : (
              "no catalogue scenario matches this incident."
            )}
          </p>
          <p className="muted">
            From the audit record of{" "}
            <time dateTime={gate.occurred_at} title={gate.occurred_at}>
              {formatLocalDateTime(gate.occurred_at)}
            </time>
            .
          </p>
        </>
      )}
    </section>
  );
}
