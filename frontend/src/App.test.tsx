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
    // The decision page reads its response window and opens a socket; no window here.
    mockFetch().mockImplementation(async (url) =>
      String(url).startsWith("/api/response-windows/")
        ? jsonResponse({ detail: "no response window" }, 404)
        : jsonResponse(HEALTH_OK),
    );
    mockWebSocket();
  });

  it("redirects / to the incident list", async () => {
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Incidents" })).toBeInTheDocument();
    await screen.findByText("API online");
  });

  it("shows the empty state on /incidents", async () => {
    renderAt("/incidents");

    expect(screen.getByText("No incidents yet.")).toBeInTheDocument();
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

  it("shows the three analyst options, disabled, on the decision page", async () => {
    renderAt("/incidents/inc-1/decision");

    for (const name of [
      "Approve recommended action (SIMULATED)",
      "Reject and release simulated isolation",
      "Select another scenario (S1 to S4, SIMULATED)",
    ]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    await screen.findByText("API online");
  });
});
