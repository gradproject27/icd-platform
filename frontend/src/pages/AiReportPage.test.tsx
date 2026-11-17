import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import summary from "../../../docs/api/examples/incident-summary.json";
import reportExample from "../../../contracts/examples/analysis-report.example.json";
import { jsonResponse, mockFetch } from "../test/fetch";
import { AiReportPage } from "./AiReportPage";

// Test data: the incident from C1's API examples and the AnalysisReport contract example.
const ID = summary.incident.incident_id;
const REPORT = { ...reportExample, incident_id: ID };
const NOT_STORED = { error: { code: "report_not_available", message: "No AI report is stored for this incident yet." } };

function serve(report: unknown, incident: Partial<typeof summary.incident> = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === `/api/incidents/${ID}`) return jsonResponse({ ...summary, incident: { ...summary.incident, ...incident } });
    if (path === `/api/incidents/${ID}/report`) return report ? jsonResponse(report) : jsonResponse(NOT_STORED, 404);
    return jsonResponse({ error: { code: "not_found", message: "No such path." } }, 404);
  });
}

function show() {
  render(
    <MemoryRouter initialEntries={[`/incidents/${ID}/report`]}>
      <Routes>
        <Route path="/incidents/:incidentId/report" element={<AiReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const section = (name: string) => screen.getByRole("region", { name });

describe("AiReportPage", () => {
  it("shows every report section on its own", async () => {
    serve(REPORT);
    show();
    expect(await screen.findByRole("region", { name: "Summary" })).toHaveTextContent(REPORT.summary);
    expect(section("Summary")).toHaveTextContent(`Attack type: ${REPORT.attack_type}`);
    expect(section("Attack sequence")).toHaveTextContent(REPORT.sequence[0]!.description);
    expect(section("Explanation")).toHaveTextContent(REPORT.risk_justification);
    expect(section("Weaknesses")).toHaveTextContent(REPORT.weaknesses[0]!);
    expect(section("Impact")).toHaveTextContent(REPORT.impact);
    expect(section("Mitigations")).toHaveTextContent(REPORT.recommendations[0]!);
    expect(section("Mitigations")).toHaveTextContent("ICD never runs these");
    expect(within(section("Mitigations")).queryByRole("button")).not.toBeInTheDocument();
    expect(section("Uncertainty")).toHaveTextContent(REPORT.uncertainty);
  });

  it("groups the findings and shows None for an empty group", async () => {
    serve(REPORT);
    show();
    const findings = await screen.findByRole("region", { name: "Findings" });
    expect(within(findings).getByRole("heading", { name: "Evidence supported" })).toBeInTheDocument();
    expect(within(findings).getByRole("heading", { name: "Likely interpretation" })).toBeInTheDocument();
    expect(within(findings).getByText("None")).toBeInTheDocument();
    expect(findings).toHaveTextContent("Evidence: none cited");
  });

  it("links every cited event ID to the incident detail page", async () => {
    serve(REPORT);
    show();
    const cited = await screen.findByRole("region", { name: "Cited evidence" });
    const links = within(cited).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["evt-0001", "evt-0002", "evt-0003"]);
    expect(links[0]).toHaveAttribute("href", `/incidents/${ID}#event-evt-0001`);
  });

  it("shows risk score, risk level and confidence in separate boxes", async () => {
    serve(REPORT);
    show();
    const boxes = await screen.findByRole("group", { name: "Risk and confidence" });
    expect(within(boxes).getByText(`${summary.incident.risk!.score} / 100`)).toBeInTheDocument();
    expect(within(boxes).getByText("High")).toBeInTheDocument();
    expect(within(boxes).getByText("82%")).toBeInTheDocument();
  });

  it("says Not determined for missing fields and marks a mock report", async () => {
    serve({ ...REPORT, generated_by: "mock", model_id: null, impact: null, weaknesses: null, sequence: null, attack_type: null });
    show();
    expect(await screen.findByText(/\[MOCK REPORT\]/)).toBeInTheDocument();
    expect(section("Impact")).toHaveTextContent("Not determined");
    expect(section("Weaknesses")).toHaveTextContent("Not determined");
    expect(section("Attack sequence")).toHaveTextContent("Not determined");
  });

  it("says no report is stored yet", async () => {
    serve(null);
    show();
    expect(await screen.findByText(/No AI report yet/)).toBeInTheDocument();
  });

  it("says when the analysis failed", async () => {
    serve(null, { analysis_status: "failed", analysis_attempts: 2 });
    show();
    expect(await screen.findByText(/failed after 2 attempts/)).toBeInTheDocument();
  });

  it("notes a confidence below 0.75", async () => {
    serve({ ...REPORT, confidence: 0.6 });
    show();
    expect(await screen.findByText(/Below 0.75/)).toBeInTheDocument();
  });
});
