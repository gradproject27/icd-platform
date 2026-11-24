import { Link, useParams } from "react-router";
import type { AnalysisReport, FindingCategory, GroundingCounts, Incident } from "../api/contracts";
import { getShownReport } from "../api/incidents";
import { PageState } from "../components/PageState";
import { formatLocalDateTime } from "../countdown/clock";
import { IncidentHeader } from "../incidents/IncidentHeader";
import { RiskAndConfidence } from "../incidents/RiskAndConfidence";
import { STUB_BANNER } from "../incidents/format";
import { useIncident } from "../incidents/useIncident";

// AI report panel (wireframes.md 4.5; Step 8). Shows the stored AnalysisReport as it is, each
// section on its own, with every cited event linked to the incident detail page. Risk score, risk
// level (C3) and confidence (the analysis) sit in three separate boxes. Recommendations are advice,
// never buttons (C-10).

const NOT_DETERMINED = "Not determined";

const FINDING_GROUPS: { category: FindingCategory; title: string }[] = [
  { category: "evidence_supported", title: "Evidence supported" },
  { category: "likely_interpretation", title: "Likely interpretation" },
  { category: "hypothesis", title: "Hypothesis" },
];

export function AiReportPage() {
  const { incidentId = "" } = useParams();
  return <ReportPanel key={incidentId} incidentId={incidentId} />;
}

function ReportPanel({ incidentId }: { incidentId: string }) {
  const { load, retry } = useIncident(incidentId, (signal) => getShownReport(incidentId, signal));
  const back = <Link to={`/incidents/${encodeURIComponent(incidentId)}`}>Back to incident</Link>;

  if (load.kind !== "ready") {
    return (
      <section>
        {back}
        <h1>AI report for incident {incidentId}</h1>
        {load.kind === "loading" ? (
          <PageState kind="loading" message="Loading report…" />
        ) : load.kind === "not_found" ? (
          <PageState kind="error" message={`Incident ${incidentId} was not found.`} />
        ) : (
          <PageState kind="error" message={load.message} onRetry={retry} />
        )}
      </section>
    );
  }

  const { summary, stub, extra: shown } = load;
  const report = shown?.report;
  return (
    <section>
      {back}
      <h1>AI report for incident {incidentId}</h1>
      {stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}
      <IncidentHeader summary={summary} />
      <RiskAndConfidence incident={summary.incident} confidence={report?.confidence ?? summary.incident.confidence} />
      {report && <Grounding grounding={report.grounding} />}
      {shown?.masked && (
        <p className="stub-banner" role="note">
          Some host, user or IP names are shown as tokens (such as host-01), because the server could not map them back
          to real values.
        </p>
      )}
      {report ? <Report incidentId={incidentId} report={report} /> : <NoReport incident={summary.incident} />}
    </section>
  );
}

/** No stored report: say why from the incident's analysis status (wireframes 4.5 states). */
function NoReport({ incident }: { incident: Incident }) {
  const attempts = incident.analysis_attempts ?? 0;
  const message =
    incident.analysis_status === "failed"
      ? `The AI analysis failed after ${attempts} attempt${attempts === 1 ? "" : "s"}. No response window is opened for a failed analysis.`
      : incident.analysis_status === "in_progress"
        ? "Analysis in progress…"
        : incident.analysis_status === "succeeded"
          ? "The analysis succeeded, but its report is not stored on the server yet."
          : "No AI report yet. The analysis has not started for this incident.";
  return <PageState kind={incident.analysis_status === "failed" ? "error" : "empty"} message={message} />;
}

/**
 * AI1's grounding counts (R2, contracts 1.3), shown as they are: how many factual claims name only
 * entities that their cited events carry (C4-D2). Nothing is recomputed here.
 */
export function Grounding({ grounding }: { grounding: GroundingCounts | null | undefined }) {
  if (!grounding) {
    return <p className="note">Grounding: not checked for this report.</p>;
  }
  const { factual_claims: factual, grounded_factual_claims: grounded, unsupported } = grounding;
  const text = `Grounding: ${grounded} of ${factual} factual claim${factual === 1 ? "" : "s"} supported by their cited events`;
  if (unsupported > 0) {
    return (
      <p className="box box--warn" role="status">
        {text} ({unsupported} unsupported: a claim names a host, user or IP its cited events do not carry). Check those
        claims against the events.
      </p>
    );
  }
  return <p className="note">{text}.</p>;
}

function Evidence({ incidentId, ids }: { incidentId: string; ids: string[] }) {
  if (ids.length === 0) return <span className="muted">Evidence: none cited</span>;
  return (
    <span className="evidence">
      Evidence:{" "}
      {ids.map((id, index) => (
        <span key={index}>
          {index > 0 && " "}
          <Link to={`/incidents/${encodeURIComponent(incidentId)}#event-${encodeURIComponent(id)}`}>{id}</Link>
        </span>
      ))}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const id = `report-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section className="box report-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

function Report({ incidentId, report }: { incidentId: string; report: AnalysisReport }) {
  const cited = [
    ...new Set([
      ...(report.sequence ?? []).flatMap((step) => step.cited_event_ids),
      ...report.findings.flatMap((finding) => finding.cited_event_ids),
    ]),
  ];
  return (
    <>
      {report.generated_by === "mock" && (
        <p className="stub-banner" role="note">
          [MOCK REPORT] Generated by the mock analyzer, not by an LLM.
        </p>
      )}
      <Section title="Summary">
        <p>{report.summary}</p>
        <p>Attack type: {report.attack_type ?? NOT_DETERMINED}</p>
      </Section>
      <Section title="Attack sequence">
        {report.sequence ? (
          <ol>
            {[...report.sequence]
              .sort((a, b) => a.order - b.order)
              .map((step, index) => (
                <li key={index}>
                  {step.description} <Evidence incidentId={incidentId} ids={step.cited_event_ids} />
                </li>
              ))}
          </ol>
        ) : (
          <p>{NOT_DETERMINED}</p>
        )}
      </Section>
      <Section title="Findings">
        {FINDING_GROUPS.map((group) => {
          const findings = report.findings.filter((finding) => finding.category === group.category);
          return (
            <div key={group.category}>
              <h3>{group.title}</h3>
              <ul>
                {findings.length === 0 ? (
                  <li>None</li>
                ) : (
                  findings.map((finding, index) => (
                    <li key={index}>
                      {finding.statement} <Evidence incidentId={incidentId} ids={finding.cited_event_ids} />
                    </li>
                  ))
                )}
              </ul>
            </div>
          );
        })}
      </Section>
      <Section title="Cited evidence">
        <p>
          <Evidence incidentId={incidentId} ids={cited} />
        </p>
      </Section>
      <Section title="Explanation">
        <p>{report.risk_justification ?? NOT_DETERMINED}</p>
      </Section>
      <Section title="Weaknesses">
        {report.weaknesses ? (
          <ul>
            {report.weaknesses.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>{NOT_DETERMINED}</p>
        )}
      </Section>
      <Section title="Impact">
        <p>{report.impact ?? NOT_DETERMINED}</p>
      </Section>
      <Section title="Mitigations">
        <p className="muted">Advice for the analyst. ICD never runs these.</p>
        {report.recommendations.length > 0 ? (
          <ul>
            {report.recommendations.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>None</p>
        )}
      </Section>
      <Section title="Uncertainty">
        <p>{report.uncertainty}</p>
      </Section>
      <p className="muted">
        Generated by {report.generated_by}, model {report.model_id ?? NOT_DETERMINED}, prompt{" "}
        {report.prompt_version ?? NOT_DETERMINED}, at{" "}
        <time dateTime={report.generated_at}>{formatLocalDateTime(report.generated_at)}</time>
      </p>
    </>
  );
}
