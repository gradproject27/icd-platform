import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import list from "../../../docs/api/examples/incident-list.json";
import type { UserRole } from "../api/contracts";
import { jsonResponse, mockFetch } from "../test/fetch";
import { ConfigurationPage } from "./ConfigurationPage";

// Test data: C1's incident list example (a real run on C3's fixture).

function serve({ role = "security_engineer", incidents }: { role?: UserRole | null; incidents?: Response } = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === "/api/me") {
      return role ? jsonResponse({ user: "dev", role }) : jsonResponse({ error: { code: "not_authenticated", message: "No user." } }, 401);
    }
    if (path === "/api/incidents") return incidents ?? jsonResponse(list);
    return jsonResponse({ error: { code: "not_found", message: "Not in this test." } }, 404);
  });
  return fetchMock;
}

function show() {
  render(
    <MemoryRouter>
      <ConfigurationPage />
    </MemoryRouter>,
  );
}

describe("ConfigurationPage", () => {
  it("counts the incidents per risk and correlation configuration version", async () => {
    serve();
    show();
    const risk = await screen.findByRole("table", { name: "Risk configuration (C3, risk.toml)" });
    const versions = new Map<string, number>();
    for (const { incident } of list.items) {
      const key = incident.risk?.config_version ?? "Not scored";
      versions.set(key, (versions.get(key) ?? 0) + 1);
    }
    for (const [version, count] of versions) {
      expect(within(risk).getByRole("rowheader", { name: version }).closest("tr")!).toHaveTextContent(String(count));
    }
    expect(screen.getByRole("table", { name: "Correlation configuration (C3, correlation.toml)" })).toBeInTheDocument();
    expect(screen.getByText(`From the ${list.items.length} stored incidents. Every value change creates a new version.`)).toBeInTheDocument();
  });

  it("never shows thresholds as literals, and says they are not served", async () => {
    serve();
    show();
    await screen.findByRole("table", { name: "Risk configuration (C3, risk.toml)" });
    expect(screen.getByText(/not served by the API yet/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/\b(40|70)\b/);
  });

  it("shows the fixed window and the simulated catalogue", async () => {
    serve({ role: "system_administrator" });
    show();
    expect(await screen.findByText("60 seconds, fixed by the server. No role can change it in the MVP (OD-17).")).toBeInTheDocument();
    const catalogue = screen.getByRole("region", { name: /Response catalogue v0/ });
    expect(within(catalogue).getAllByRole("rowheader").map((cell) => cell.textContent)).toEqual(["S1", "S2", "S3", "S4"]);
    expect(catalogue).toHaveTextContent("[SIMULATED]");
  });

  it("shows the empty state with no incidents", async () => {
    serve({ incidents: jsonResponse({ items: [] }) });
    show();
    expect(await screen.findByText("No incidents yet, so no configuration version is in use.")).toBeInTheDocument();
  });

  it("shows the error block with Retry when the incidents cannot be read", async () => {
    serve({ incidents: jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500) });
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the configuration versions. Boom.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it.each<UserRole>(["soc_analyst", "soc_manager"])("is not shown to the %s, and reads nothing", async (role) => {
    const fetchMock = serve({ role });
    show();
    expect(await screen.findByRole("note")).toHaveTextContent(
      "Only the Security Engineer and System Administrator can view the configuration.",
    );
    expect(fetchMock.mock.calls.map(([url]) => String(url))).not.toContain("/api/incidents");
  });

  it("is not shown when the API does not say who the user is", async () => {
    serve({ role: null });
    show();
    expect(await screen.findByRole("note")).toHaveTextContent("The API did not say who you are.");
  });
});
