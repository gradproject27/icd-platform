import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import eventList from "../../../docs/api/examples/incident-event-list.json";
import summary from "../../../docs/api/examples/incident-summary.json";
import reportExample from "../../../contracts/examples/analysis-report.example.json";
import { jsonResponse, mockFetch } from "../test/fetch";
import { IncidentDetailPage } from "./IncidentDetailPage";

// Test data: C1's API examples, written from a real run of the backend on C3's fixture.
const ID = summary.incident.incident_id;
const FIRST = eventList.items[0]!.event.event_id;
const NOT_STORED = { error: { code: "report_not_available", message: "No AI report is stored for this incident yet." } };

interface Api {
  summary?: unknown;
  events?: unknown;
  report?: unknown;
  original?: Response;
}

function serve(api: Api = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === `/api/incidents/${ID}`) return api.summary instanceof Response ? api.summary : jsonResponse(api.summary ?? summary);
    if (path === `/api/incidents/${ID}/events`) return api.events instanceof Response ? api.events : jsonResponse(api.events ?? eventList);
    if (path === `/api/incidents/${ID}/report`) return api.report ? jsonResponse(api.report) : jsonResponse(NOT_STORED, 404);
    if (path.startsWith(`/api/incidents/${ID}/events/`) && path.endsWith("/original")) {
      return api.original ?? jsonResponse({ event_id: FIRST, record_ref: "events.json:2", source_file: "events.json", line: "raw line two" });
    }
    return jsonResponse({ error: { code: "not_found", message: "No such path." } }, 404);
  });
  return fetchMock;
}

function show(path = `/incidents/${ID}`) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/incidents/:incidentId" element={<IncidentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("IncidentDetailPage", () => {
  it("shows the header, the three risk boxes and the factor table from the API", async () => {
    serve();
    show();
    expect(await screen.findByRole("heading", { name: `Incident ${ID}` })).toBeInTheDocument();
    const boxes = screen.getByRole("group", { name: "Risk and confidence" });
    expect(within(boxes).getByText(`${summary.incident.risk!.score} / 100`)).toBeInTheDocument();
    expect(within(boxes).getByText("High")).toBeInTheDocument();
    expect(within(boxes).getByText("Not available")).toBeInTheDocument();
    for (const factor of summary.incident.risk!.factors) {
      expect(screen.getByRole("rowheader", { name: factor.name })).toBeInTheDocument();
    }
    expect(screen.getByText("Justification: Not determined")).toBeInTheDocument();
    expect(screen.queryByText(/STUB DATA/)).not.toBeInTheDocument();
  });

  it("lists the events oldest first as a timeline with role, link keys and fields", async () => {
    serve();
    show();
    const timeline = await screen.findByRole("list", { name: "Event timeline" });
    const items = within(timeline).getAllByRole("listitem");
    expect(items).toHaveLength(eventList.items.length);
    expect(items[0]!).toHaveTextContent("FLAGGED");
    expect(items[0]!).toHaveTextContent("Linked by (first)");
    expect(items[0]!).toHaveTextContent("start");
    expect(screen.getByRole("heading", { name: `Related events (${eventList.items.length})` })).toBeInTheDocument();
  });

  it("reads the original record of an event on request", async () => {
    serve();
    show();
    const [button] = await screen.findAllByRole("button", { name: "Show original record" });
    fireEvent.click(button!);
    expect(await screen.findByText("raw line two")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide original record" }));
    expect(screen.queryByText("raw line two")).not.toBeInTheDocument();
  });

  it("says when the original record is not available", async () => {
    serve({
      original: jsonResponse({ error: { code: "original_not_available", message: "The uploaded file for this event is no longer stored." } }, 404),
    });
    show();
    const [button] = await screen.findAllByRole("button", { name: "Show original record" });
    fireEvent.click(button!);
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer stored");
  });

  it("shows the risk justification when a report is stored", async () => {
    serve({ report: { ...reportExample, incident_id: ID } });
    show();
    expect(await screen.findByText(`Justification: ${reportExample.risk_justification}`)).toBeInTheDocument();
  });

  it("marks the event a report cites", async () => {
    serve();
    show(`/incidents/${ID}#event-${FIRST}`);
    const timeline = await screen.findByRole("list", { name: "Event timeline" });
    const item = within(timeline).getAllByRole("listitem")[0]!;
    expect(within(item).getByLabelText("Cited event")).toBeInTheDocument();
  });

  it("links to the pending decision only while a decision is open", async () => {
    serve({ summary: { ...summary, incident: { ...summary.incident, status: "awaiting_human_decision" } } });
    show();
    expect(await screen.findByRole("link", { name: "Pending decision" })).toBeInTheDocument();
  });

  it("has no decision link for a new incident", async () => {
    serve({ summary: { ...summary, incident: { ...summary.incident, status: "new" } } });
    show();
    await screen.findByRole("link", { name: "AI report" });
    expect(screen.queryByRole("link", { name: "Pending decision" })).not.toBeInTheDocument();
  });

  it("says when the risk is not scored", async () => {
    serve({ summary: { ...summary, incident: { ...summary.incident, risk: null } } });
    show();
    expect(await screen.findByText(/Risk not scored yet/)).toBeInTheDocument();
  });

  it("shows not found without Retry, and an error with Retry", async () => {
    serve({ summary: jsonResponse({ error: { code: "not_found", message: "x" } }, 404) });
    show();
    expect(await screen.findByText(`Incident ${ID} was not found.`)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("offers Retry when the events cannot be read", async () => {
    serve({ events: jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500) });
    show();
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
