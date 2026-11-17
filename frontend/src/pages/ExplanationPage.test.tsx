import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import trail from "../../../docs/api/examples/audit-trail.json";
import eventList from "../../../docs/api/examples/incident-event-list.json";
import summary from "../../../docs/api/examples/incident-summary.json";
import reportExample from "../../../contracts/examples/analysis-report.example.json";
import { jsonResponse, mockFetch } from "../test/fetch";
import { ExplanationPage } from "./ExplanationPage";

// Test data: C1's API examples (a real run on C3's fixture: High 100, a freeze, S2 recommended)
// and the AnalysisReport contract example for the justification.
const ID = summary.incident.incident_id;
const NOT_STORED = { error: { code: "report_not_available", message: "No AI report is stored for this incident yet." } };

interface Api {
  summary?: unknown;
  audit?: Response;
  report?: unknown;
  events?: Response;
}

function serve(api: Api = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === `/api/incidents/${ID}`) return jsonResponse(api.summary ?? summary);
    if (path === `/api/incidents/${ID}/events`) return api.events ?? jsonResponse(eventList);
    if (path === `/api/incidents/${ID}/audit`) return api.audit ?? jsonResponse(trail);
    if (path === `/api/incidents/${ID}/report`) return api.report ? jsonResponse(api.report) : jsonResponse(NOT_STORED, 404);
    return jsonResponse({ error: { code: "not_found", message: "No incident with this ID exists." } }, 404);
  });
}

function show(id = ID) {
  render(
    <MemoryRouter initialEntries={[`/incidents/${id}/explanation`]}>
      <Routes>
        <Route path="/incidents/:incidentId/explanation" element={<ExplanationPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const section = (name: string) => screen.getByRole("region", { name });

describe("ExplanationPage", () => {
  it("explains the score with labelled factors, assumptions, evidence and the configuration", async () => {
    serve();
    show();
    await screen.findByRole("heading", { name: "Why this risk score" });
    const score = section("Why this risk score");
    expect(score).toHaveTextContent("High 100 / 100");
    const likelihood = within(score).getByRole("rowheader", { name: "Evidence strength (L)" });
    expect(likelihood).toHaveAttribute("title", "likelihood");
    expect(likelihood.closest("tr")!).toHaveTextContent("+99.8");
    expect(within(score).getByRole("rowheader", { name: "Points removed by the asset's impact (I)" })).toBeInTheDocument();
    expect(score).toHaveTextContent("Outcome not in the data: treated as succeeded");
    expect(within(score).getByRole("link", { name: "fx-008" })).toHaveAttribute("href", `/incidents/${ID}#event-fx-008`);
    expect(score).toHaveTextContent("Risk configuration risk-v0");
    expect(score).toHaveTextContent("Justification (written by the AI): Not determined: no AI report is stored yet.");
  });

  it("shows the AI justification when a report is stored", async () => {
    serve({ report: reportExample });
    show();
    await screen.findByRole("heading", { name: "Why this risk score" });
    expect(section("Why this risk score")).toHaveTextContent(
      `Justification (written by the AI): ${reportExample.risk_justification ?? "Not determined"}`,
    );
  });

  it("explains the grouping from the events' roles and link keys", async () => {
    serve();
    show();
    await screen.findByRole("heading", { name: "Why these events are grouped" });
    const grouping = section("Why these events are grouped");
    expect(grouping).toHaveTextContent("3 events: 2 flagged by the dataset label, 1 context.");
    expect(within(grouping).getByRole("link", { name: "fx-002" })).toBeInTheDocument();
    const host = within(grouping).getByRole("rowheader", { name: "Same host" }).closest("tr")!;
    expect(host).toHaveTextContent("2");
    expect(grouping).toHaveTextContent("Correlation configuration correlation-v1");
  });

  it("explains the response window from C5's freeze-gate record, with the recommendation as advice", async () => {
    serve();
    show();
    await screen.findByRole("heading", { name: "Why there is or is not a response window" });
    const why = section("Why there is or is not a response window");
    expect(why).toHaveTextContent("A 60-second response window was opened");
    expect(why).toHaveTextContent("risk level High, confidence 90%");
    expect(why).toHaveTextContent("S2 Isolate the host and block the source IP [SIMULATED]");
    expect(why).toHaveTextContent("not chosen by the AI");
  });

  it("lists the reasons when no window was opened", async () => {
    const items = trail.items.map((record) =>
      record.details && "freeze" in record.details
        ? { ...record, details: { ...record.details, freeze: false, reasons: "risk_not_high,confidence_below_threshold", recommended_scenario_id: null } }
        : record,
    );
    serve({ audit: jsonResponse({ items }) });
    show();
    await screen.findByRole("heading", { name: "Why there is or is not a response window" });
    const why = section("Why there is or is not a response window");
    expect(why).toHaveTextContent("No response window was opened");
    expect(why).toHaveTextContent("Risk level is not High");
    expect(why).toHaveTextContent("Confidence is below 0.75");
    expect(why).toHaveTextContent("no catalogue scenario matches this incident.");
  });

  it("says when the incident is not analysed yet, or the trail cannot be read", async () => {
    serve({ audit: jsonResponse({ items: [] }) });
    show();
    expect(await screen.findByText(/Not analysed yet/)).toBeInTheDocument();
  });

  it("keeps the page when only the audit trail fails", async () => {
    serve({ audit: jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500) });
    show();
    expect(await screen.findByText("Could not read the audit trail, where the response engine records this.")).toBeInTheDocument();
    expect(section("Why this risk score")).toHaveTextContent("High 100 / 100");
  });

  it("says when the risk is not scored", async () => {
    serve({ summary: { ...summary, incident: { ...summary.incident, risk: null } } });
    show();
    expect(await screen.findByText(/Risk not scored yet/)).toBeInTheDocument();
  });

  it("shows the error block with Retry when the events cannot be read", async () => {
    serve({ events: jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500) });
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent(`Could not load incident ${ID}. Boom.`);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows not found for an unknown incident", async () => {
    serve();
    show("inc-unknown");
    expect(await screen.findByRole("alert")).toHaveTextContent("Incident inc-unknown was not found.");
  });
});
