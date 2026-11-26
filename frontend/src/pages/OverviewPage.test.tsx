import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import stubData from "../../dev/stub-data/incidents.json";
import type { IncidentSummary } from "../api/proposed";
import { STUB_BANNER } from "../incidents/format";
import { mockWebSocket } from "../test/fakeWebSocket";
import { jsonResponse, mockFetch } from "../test/fetch";
import { LIVE_COUNTDOWNS, OverviewPage, RECENT_DECISION_HOURS } from "./OverviewPage";

const items = stubData.items.map(({ incident, entities }) => ({ incident, entities })) as IncidentSummary[];

const ENTITY_RISK = {
  schema_version: "1.0",
  config_version: "entity-risk-v1",
  tactics_config_version: "tactics-v1",
  score_threshold: 70,
  tactics_threshold: 3,
  window_start: null,
  window_end: null,
  items: ["ws-80", "10.10.1.21", "203.0.113.10", "svc-db", "ws-50", "ws-51"].map((entity, index) => ({
    entity,
    score: 56 - index * 5,
    level: index < 4 ? "medium" : "low",
    incident_count: index + 1,
    incidents: [],
    tactics: [],
    flags: [],
  })),
};

const RECENT = {
  schema_version: "1.0",
  hours: 24,
  since: "2026-11-25T10:00:00Z",
  until: "2026-11-26T10:00:00Z",
  items: [
    {
      record_id: "aud-1",
      occurred_at: "2026-11-26T09:00:00Z",
      incident_id: "inc-stub-07",
      decision: "approve",
      scenario_id: "S2",
      by: "analyst",
      actor: "analyst-dev",
      actor_role: "soc_analyst",
      comment: null,
    },
    {
      record_id: "aud-2",
      occurred_at: "2026-11-26T08:00:00Z",
      incident_id: "inc-stub-09",
      decision: "system_selection",
      scenario_id: "S1",
      by: "system",
      actor: "system",
      actor_role: null,
      comment: null,
    },
  ],
};

const NOTIFICATIONS = {
  items: [
    {
      record_id: "aud-9",
      occurred_at: "2026-11-26T09:30:00Z",
      incident_id: "inc-stub-01",
      event_type: "notification.sent",
      actor: "system",
      result: "success",
      details: { reason: "made-up-reason" },
    },
  ],
};

type Overrides = Partial<Record<"incidents" | "entities" | "decisions" | "notifications", () => Response>>;

function serve(list: IncidentSummary[] = items, overrides: Overrides = {}, headers: Record<string, string> = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === "/api/incidents") {
      return (
        overrides.incidents?.() ??
        new Response(JSON.stringify({ items: list }), { headers: { "Content-Type": "application/json", ...headers } })
      );
    }
    if (path.startsWith("/api/entity-risk")) return overrides.entities?.() ?? jsonResponse(ENTITY_RISK);
    if (path.startsWith("/api/decisions/recent")) return overrides.decisions?.() ?? jsonResponse(RECENT);
    if (path.startsWith("/api/notifications")) return overrides.notifications?.() ?? jsonResponse(NOTIFICATIONS);
    if (path.startsWith("/api/response-windows/")) return jsonResponse({ detail: "no response window" }, 404);
    return jsonResponse({ error: { code: "not_found", message: "Not here." } }, 404);
  });
  mockWebSocket();
  return fetchMock;
}

async function renderOverview() {
  const view = render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  );
  await screen.findByRole("link", { name: /^Incidents/ });
  // Let the panels' own reads and the countdowns settle.
  await act(async () => {});
  return view;
}

const panel = (name: string) => screen.getByRole("region", { name });

describe("OverviewPage", () => {
  beforeEach(() => {
    serve();
  });

  it("shows the four KPI tiles, each a link to the list filtered the same way", async () => {
    await renderOverview();
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    const tile = (label: RegExp) => screen.getByRole("link", { name: label });
    expect(tile(/^Incidents 13/)).toHaveAttribute("href", "/incidents");
    expect(tile(/^Awaiting human decision \[SIMULATED\] 5/)).toHaveAttribute("href", "/incidents?state=awaiting_human_decision");
    expect(tile(/^High risk 5/)).toHaveAttribute("href", "/incidents?level=high");
    expect(tile(/^Escalated 1/)).toHaveAttribute("href", "/incidents?state=escalated");
  });

  it("counts by risk level in a table, text first, each count a filtered link", async () => {
    await renderOverview();
    const table = within(panel("Incidents by risk level")).getByRole("table", { name: "Incidents by risk level" });
    const rows = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.textContent);
    expect(rows).toEqual(["High5", "Medium4", "Low2", "Not scored2"]);
    expect(within(table).getByRole("link", { name: "5 High incidents" })).toHaveAttribute("href", "/incidents?level=high");
    expect(within(table).getByRole("link", { name: "2 Not scored incidents" })).toHaveAttribute(
      "href",
      "/incidents?level=none",
    );
    expect(within(panel("Incidents by risk level")).getByText(/only counts them/)).toBeInTheDocument();
  });

  it("counts by state with a text legend and a described chart", async () => {
    await renderOverview();
    const region = panel("Incidents by state");
    expect(within(region).getByRole("img")).toHaveAccessibleName(
      "Incidents by state: New 2, Under Analysis 2, Awaiting Human Decision 5, Response in Progress 1, Escalated 1, Resolved 1, Closed 1",
    );
    expect(within(region).getByRole("link", { name: "1 Escalated incidents" })).toHaveAttribute(
      "href",
      "/incidents?state=escalated",
    );
  });

  it("shows incidents over time in dataset time, with a table alternative", async () => {
    await renderOverview();
    const region = panel("Incidents over time (dataset time)");
    expect(within(region).getByRole("img").getAttribute("aria-label")).toMatch(/^Incidents by first event per hour, from /);
    expect(within(region).getByText("Show as table")).toBeInTheDocument();
    const cells = within(region).getAllByRole("row").slice(1);
    const total = cells.reduce((sum, row) => sum + Number(within(row).getAllByRole("cell")[1]!.textContent), 0);
    expect(total).toBe(13);
  });

  it("lists the awaiting incidents newest first, each with the existing countdown and a decision link", async () => {
    await renderOverview();
    const region = panel("Needs your decision now [SIMULATED]");
    const links = within(region)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("href")?.endsWith("/decision"));
    expect(links.map((link) => link.textContent)).toEqual([
      "inc-stub-12",
      "inc-stub-02",
      "inc-stub-04",
      "inc-stub-03",
      "inc-stub-01",
    ]);
    expect(links[0]).toHaveAttribute("href", "/incidents/inc-stub-12/decision");
    expect(within(region).getByText("High 82")).toBeInTheDocument();
    expect(await within(region).findAllByText("No response window. No automatic action will run.")).toHaveLength(5);
    expect(within(region).getByRole("link", { name: "All awaiting" })).toHaveAttribute(
      "href",
      "/incidents?state=awaiting_human_decision",
    );
  });

  it("gives each countdown its own heading id", async () => {
    await renderOverview();
    const sections = await within(panel("Needs your decision now [SIMULATED]")).findAllByRole("region", { name: "Response window" });
    const ids = sections.map((section) => section.getAttribute("aria-labelledby"));
    expect(new Set(ids).size).toBe(ids.length);
  });

  it(`shows a live countdown on the first ${LIVE_COUNTDOWNS} only and links the rest`, async () => {
    const many = items.map((item, index) => ({
      ...item,
      incident: { ...item.incident, status: index < 8 ? ("awaiting_human_decision" as const) : ("resolved" as const) },
    }));
    serve(many);
    await renderOverview();
    const region = panel("Needs your decision now [SIMULATED]");
    expect(await within(region).findAllByRole("region", { name: "Response window" })).toHaveLength(LIVE_COUNTDOWNS);
    expect(within(region).getByText(/^3 more awaiting a decision/)).toBeInTheDocument();
  });

  it("shows the top five entities, level text before the score", async () => {
    await renderOverview();
    const region = panel("Entities with the highest risk");
    const rows = within(region).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(5);
    expect(within(rows[0]!).getByText("Medium 56")).toBeInTheDocument();
    expect(within(region).queryByText("ws-51")).not.toBeInTheDocument();
    expect(within(region).getByRole("link", { name: "All entities" })).toHaveAttribute("href", "/entities");
  });

  it(`shows the decisions of the last ${RECENT_DECISION_HOURS} hours, scenarios marked SIMULATED`, async () => {
    const fetchMock = serve();
    await renderOverview();
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain(`/api/decisions/recent?hours=${RECENT_DECISION_HOURS}`);
    const region = panel(`Simulated decisions in the last ${RECENT_DECISION_HOURS} hours`);
    const lines = within(region).getAllByRole("listitem");
    expect(lines[0]).toHaveTextContent("inc-stub-07 Approved S2 [SIMULATED] by analyst-dev");
    expect(lines[1]).toHaveTextContent("inc-stub-09 Selected by the system at the deadline S1 [SIMULATED] by System");
  });

  it("shows the latest notifications with their incident", async () => {
    await renderOverview();
    const region = panel("Latest notifications");
    expect(within(region).getByText("made-up-reason")).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: "inc-stub-01" })).toHaveAttribute("href", "/incidents/inc-stub-01");
  });

  it("shows the STUB banner when the list came from the stub server", async () => {
    serve(items, {}, { "X-ICD-Stub": "1" });
    await renderOverview();
    expect(screen.getByRole("note")).toHaveTextContent(STUB_BANNER);
  });

  it("has an empty state with no incidents", async () => {
    serve([]);
    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("No incidents yet. Upload a dataset to start.")).toBeInTheDocument();
    expect(screen.getByText("No incident is awaiting a human decision.")).toBeInTheDocument();
    await act(async () => {});
  });

  it("shows an error with Retry when the incidents cannot be read, then recovers", async () => {
    let fail = true;
    serve(items, {
      incidents: () =>
        fail
          ? jsonResponse({ error: { code: "internal_error", message: "Database down." } }, 500)
          : jsonResponse({ items }),
    });
    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    );
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0]).toHaveTextContent("Could not load incidents.");
    fail = false;
    fireEvent.click(within(alerts[0]!).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: /^High risk 5/ })).toBeInTheDocument();
    await act(async () => {});
  });

  it("keeps the other panels when one read fails", async () => {
    serve(items, { entities: () => jsonResponse({ error: { code: "internal_error", message: "No roll-up." } }, 500) });
    await renderOverview();
    expect(within(panel("Entities with the highest risk")).getByRole("alert")).toHaveTextContent(
      "Could not load the entity risk.",
    );
    expect(within(panel("Latest notifications")).getByText("made-up-reason")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^High risk 5/ })).toBeInTheDocument();
  });

  it("has empty texts for entities, decisions and notifications", async () => {
    serve(items, {
      entities: () => jsonResponse({ ...ENTITY_RISK, items: [] }),
      decisions: () => jsonResponse({ ...RECENT, items: [] }),
      notifications: () => jsonResponse({ items: [] }),
    });
    await renderOverview();
    expect(screen.getByText("No entity has a risk roll-up yet.")).toBeInTheDocument();
    expect(screen.getByText("No decision in the last 24 hours.")).toBeInTheDocument();
    expect(screen.getByText("No notifications.")).toBeInTheDocument();
  });
});
