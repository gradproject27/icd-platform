import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import eventList from "../../../docs/api/examples/incident-event-list.json";
import summary from "../../../docs/api/examples/incident-summary.json";
import type { IncidentEventItem } from "../api/proposed";
import { buildGraph, GRAPH_MAX_EVENTS } from "../incidents/graph";
import { jsonResponse, mockFetch } from "../test/fetch";
import { EntityGraphPage } from "./EntityGraphPage";

// Test data: C1's API examples. Three events on web-01: fx-002 (flagged, first), fx-003 (context,
// linked by host) and fx-004 (flagged, linked by host and ip_pair).
const ID = summary.incident.incident_id;
const ITEMS = eventList.items as IncidentEventItem[];

function serve(events?: Response) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === `/api/incidents/${ID}`) return jsonResponse(summary);
    if (path === `/api/incidents/${ID}/events`) return events ?? jsonResponse(eventList);
    return jsonResponse({ error: { code: "not_found", message: "No such incident." } }, 404);
  });
}

function show() {
  render(
    <MemoryRouter initialEntries={[`/incidents/${ID}/graph`]}>
      <Routes>
        <Route path="/incidents/:incidentId/graph" element={<EntityGraphPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("buildGraph", () => {
  it("joins each event to the hosts, users and IPs it names, marking the link-key edges", () => {
    const graph = buildGraph(ITEMS);
    expect(graph.entities.map((entity) => entity.id)).toEqual([
      "host:web-01",
      "ip:10.10.1.21",
      "ip:10.10.5.5",
      "ip:203.0.113.10",
    ]);
    expect(graph.edges).toHaveLength(9);
    expect(graph.edges.filter((edge) => edge.linkedBy).map((edge) => `${edge.eventId} ${edge.field}`)).toEqual([
      "fx-003 host",
      "fx-004 host",
      "fx-004 src_ip",
      "fx-004 dst_ip",
    ]);
  });

  it("draws at most the first events and keeps the total", () => {
    const many = Array.from({ length: GRAPH_MAX_EVENTS + 5 }, (_, index) => ({
      ...ITEMS[0]!,
      event: { ...ITEMS[0]!.event, event_id: `ev-${index}` },
    }));
    const graph = buildGraph(many);
    expect(graph.events).toHaveLength(GRAPH_MAX_EVENTS);
    expect(graph.total).toBe(GRAPH_MAX_EVENTS + 5);
  });
});

describe("EntityGraphPage", () => {
  it("draws the graph with roles in text, and lists every line in a table", async () => {
    serve();
    show();
    const svg = await screen.findByRole("img", { name: /Entity graph: 3 events and 4 hosts, users and IPs/ });
    expect(svg).toHaveTextContent("FLAGGED fx-002");
    expect(svg).toHaveTextContent("context fx-003");
    expect(svg).toHaveTextContent("host web-01");
    expect(svg.querySelectorAll("line")).toHaveLength(9);
    expect(svg.querySelectorAll("line.graph__edge--linked")).toHaveLength(4);

    const table = screen.getByRole("table", { name: "Every line of the graph" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(9);
    expect(rows.filter((row) => row.textContent?.includes("Yes: Same host"))).toHaveLength(2);
    expect(rows.filter((row) => row.textContent?.includes("Yes: Same source and destination IP"))).toHaveLength(2);
  });

  it("asks for a retry when no event can be read", async () => {
    serve(jsonResponse({ items: [] }));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("No related events to show.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows the error block with Retry when the events cannot be read", async () => {
    serve(jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent(`Could not load incident ${ID}. Boom.`);
  });
});
