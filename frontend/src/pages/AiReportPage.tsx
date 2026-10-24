import { Link, useParams } from "react-router";

// Sections follow the AnalysisReport contract (contracts/schemas/analysis-report.schema.json).
const SECTIONS = [
  { title: "Summary", text: "A short explanation of what happened." },
  { title: "Attack sequence", text: "The ordered steps of the attack, each citing its events." },
  {
    title: "Findings",
    text: "Each finding with its category: evidence supported, likely interpretation or hypothesis.",
  },
  { title: "Cited evidence", text: "The event IDs the report cites, all from the evidence package." },
  { title: "Confidence", text: "How confident the analysis is." },
  { title: "Uncertainty", text: "What the analysis could not establish." },
];

export function AiReportPage() {
  const { incidentId } = useParams();

  return (
    <section>
      <h1>AI report for incident {incidentId}</h1>
      <p>This page will show the AI analysis of the incident, with every statement tied to evidence.</p>
      <Link to={`/incidents/${encodeURIComponent(incidentId ?? "")}`}>Back to incident</Link>
      {SECTIONS.map((section) => (
        <section className="placeholder" key={section.title}>
          <h2>{section.title}</h2>
          <p>{section.text}</p>
        </section>
      ))}
    </section>
  );
}
