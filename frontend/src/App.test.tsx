import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";
import { mockWebSocket } from "./test/fakeWebSocket";
import { HEALTH_OK, jsonResponse, mockFetch } from "./test/fetch";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("routing", () => {
  beforeEach(() => {
    // The decision page reads its response window and opens a socket; no window here. The
    // incident list gets an empty list.
    mockFetch().mockImplementation(async (url) => {
      const path = String(url);
      if (path.startsWith("/api/response-windows/")) return jsonResponse({ detail: "no response window" }, 404);
      if (path === "/api/incidents") return jsonResponse({ items: [] });
      if (path.startsWith("/api/incidents/")) {
        return jsonResponse({ error: { code: "not_found", message: "No incident with ID inc-1 exists." } }, 404);
      }
      return jsonResponse(HEALTH_OK);
    });
    mockWebSocket();
  });

  it("redirects / to the incident list", async () => {
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Incidents" })).toBeInTheDocument();
    await screen.findByText("API online");
  });

  it("shows the empty state on /incidents", async () => {
    renderAt("/incidents");

    expect(await screen.findByText("No incidents yet. Upload a dataset to start.")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    await screen.findByText("API online");
  });

  it("renders /login without the layout navigation", () => {
    renderAt("/login");

    expect(screen.getByRole("heading", { name: "Sign in to ICD" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("shows the not-found page for an unknown path", async () => {
    renderAt("/no-such-page");

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    await screen.findByText("API online");
  });

  it("routes to the decision page, which reports an unknown incident as not found", async () => {
    renderAt("/incidents/inc-1/decision");

    expect(screen.getByRole("heading", { name: "Pending decision for incident inc-1" })).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("No incident with ID inc-1 exists.");
    expect(screen.getByRole("link", { name: "Back to incident" })).toHaveAttribute("href", "/incidents/inc-1");
    await screen.findByText("API online");
  });
});
