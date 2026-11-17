import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import trail from "../../../docs/api/examples/audit-trail.json";
import summary from "../../../docs/api/examples/incident-summary.json";
import type { UserRole } from "../api/contracts";
import { jsonResponse, mockFetch } from "../test/fetch";
import { AuditTrailPage } from "./AuditTrailPage";

// Test data: C1's API examples, from a real run on C3's fixture: one incident through a freeze,
// an approve, the simulated action and a refused second decision.
const ID = summary.incident.incident_id;

function serve({ role = "soc_analyst", audit }: { role?: UserRole | null; audit?: Response } = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === "/api/me") {
      return role ? jsonResponse({ user: "dev", role }) : jsonResponse({ error: { code: "not_authenticated", message: "No user." } }, 401);
    }
    if (path === `/api/incidents/${ID}`) return jsonResponse(summary);
    if (path === `/api/incidents/${ID}/audit`) return audit ?? jsonResponse(trail);
    return jsonResponse({ error: { code: "not_found", message: "No such incident." } }, 404);
  });
  return fetchMock;
}

function show(path = `/incidents/${ID}/audit`) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/incidents/:incidentId/audit" element={<AuditTrailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const rows = async () => {
  const table = await screen.findByRole("table");
  return within(table).getAllByRole("row").slice(1);
};

describe("AuditTrailPage", () => {
  it("lists C5's records in written order with labels, actors, results and details", async () => {
    serve();
    show();
    const body = await rows();
    expect(body).toHaveLength(trail.items.length);
    expect(body[0]!).toHaveTextContent("Status changed");
    expect(body[0]!).toHaveTextContent("cause");
    expect(body[0]!).toHaveTextContent("incident created by correlation");
    expect(body[6]!).toHaveTextContent("Decision recorded");
    expect(body[6]!).toHaveTextContent("analyst-dev (SOC Analyst)");
    expect(body[10]!).toHaveTextContent("Refused");
    expect(screen.getByText(`${trail.items.length} of ${trail.items.length} records`)).toBeInTheDocument();
  });

  it("marks every simulated action SIMULATED, and nothing else", async () => {
    serve();
    show();
    const body = await rows();
    const marked = body.filter((row) => row.textContent?.includes("[SIMULATED]"));
    expect(marked).toHaveLength(trail.items.filter((record) => record.simulated).length);
    marked.forEach((row) => expect(row).toHaveTextContent("Action simulated"));
  });

  it("filters by event group, actor and result, and clears the filters", async () => {
    serve();
    show();
    await rows();
    fireEvent.change(screen.getByLabelText("Event"), { target: { value: "actions" } });
    expect(await rows()).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Event"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Actor"), { target: { value: "user" } });
    expect(await rows()).toHaveLength(trail.items.filter((record) => record.actor !== "system").length);
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "ignored" } });
    expect(screen.getByText("No audit records match these filters.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await rows()).toHaveLength(trail.items.length);
  });

  it("keeps the filters from the URL", async () => {
    serve();
    show(`/incidents/${ID}/audit?group=notifications`);
    const body = await rows();
    expect(body).toHaveLength(1);
    expect(body[0]!).toHaveTextContent("Notification sent");
  });

  it("shows the empty state for an incident the engine does not track yet", async () => {
    serve({ audit: jsonResponse({ items: [] }) });
    show();
    expect(await screen.findByText(/No audit records for this incident yet/)).toBeInTheDocument();
  });

  it("shows the error block with Retry when the trail cannot be read", async () => {
    serve({ audit: jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500) });
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent(`Could not load incident ${ID}. Boom.`);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows the System Administrator the trail", async () => {
    serve({ role: "system_administrator" });
    show();
    expect(await rows()).toHaveLength(trail.items.length);
  });

  it.each<UserRole>(["soc_manager", "security_engineer"])("does not show the %s the trail, and reads nothing", async (role) => {
    const fetchMock = serve({ role });
    show();
    expect(await screen.findByRole("note")).toHaveTextContent(
      "Only the SOC Analyst and System Administrator can view audit records.",
    );
    expect(fetchMock.mock.calls.map(([url]) => String(url))).not.toContain(`/api/incidents/${ID}/audit`);
  });

  it("does not show the trail when the API does not say who the user is", async () => {
    serve({ role: null });
    show();
    expect(await screen.findByRole("note")).toHaveTextContent("The API did not say who you are.");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
