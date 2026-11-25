import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import example from "../../../docs/api/examples/entity-risk-list.json";
import { jsonResponse, mockFetch } from "../test/fetch";
import { EntityRiskPage } from "./EntityRiskPage";

// Test data: the API example, written from the backend's roll-up of C3's correlation fixture.

function serve(answer: Response | unknown = example) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) =>
    String(url).startsWith("/api/entity-risk")
      ? answer instanceof Response
        ? answer
        : jsonResponse(answer)
      : jsonResponse({ error: { code: "not_found", message: "x" } }, 404),
  );
  return fetchMock;
}

function show(path = "/entities") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/entities" element={<EntityRiskPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("EntityRiskPage", () => {
  it("lists entities highest score first with level, incidents, tactics and flags", async () => {
    serve();
    show();
    const table = await screen.findByRole("table", { name: "Entities, highest score first" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]!).getByRole("rowheader")).toHaveTextContent("10.10.1.21");
    const ws80 = within(table).getByRole("rowheader", { name: "ws-80" }).closest("tr")!;
    expect(ws80).toHaveTextContent("19 / 100");
    expect(ws80).toHaveTextContent("TA0001, TA0003, TA0011, TA0043");
    expect(ws80).toHaveTextContent("Tactic threshold reached");
    expect(within(ws80).getAllByRole("link")[0]).toHaveAttribute("href", expect.stringMatching(/^\/incidents\/inc-/));
  });

  it("says the view is read-only and names its configuration", async () => {
    serve();
    show();
    await screen.findByRole("table");
    expect(screen.getByText(/never changes an incident's score/)).toBeInTheDocument();
    expect(screen.getByText(/Configuration entity-risk-v1, tactics tactics-v1/)).toBeInTheDocument();
  });

  it("asks for one upload when the URL names it", async () => {
    const fetchMock = serve({ ...example, items: [] });
    show("/entities?upload_id=upl-1");
    expect(await screen.findByText(/No scored incident yet/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/entity-risk?upload_id=upl-1", expect.anything());
  });

  it("shows an error with Retry when the API cannot answer", async () => {
    serve(jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the entity risk.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
