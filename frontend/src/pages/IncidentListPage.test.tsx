import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";
import stubData from "../../dev/stub-data/incidents.json";
import type { IncidentSummary } from "../api/proposed";
import { formatLocalDateTime } from "../countdown/clock";
import { STUB_BANNER } from "../incidents/format";
import { jsonResponse, mockFetch } from "../test/fetch";
import { IncidentListPage } from "./IncidentListPage";

// Test data: the committed stub incidents, served as the stub server serves them.
const items = stubData.items.map(({ incident, entities }) => ({ incident, entities })) as IncidentSummary[];

function stubResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json", "X-ICD-Stub": "1" },
  });
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderAt(path = "/incidents") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/incidents"
          element={
            <>
              <IncidentListPage />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

const ids = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[0]!.textContent);

const rowOf = (id: string) => screen.getByRole("link", { name: id }).closest("tr")!;

async function renderStub(path?: string) {
  mockFetch().mockImplementation(async () => stubResponse({ items }));
  renderAt(path);
  await screen.findByRole("table");
}

describe("IncidentListPage", () => {
  it("renders the 13 stub incidents, newest first, under the STUB banner", async () => {
    await renderStub();

    expect(screen.getByRole("note")).toHaveTextContent(STUB_BANNER);
    expect(ids()).toEqual([
      "inc-stub-13",
      "inc-stub-12",
      "inc-stub-10",
      "inc-stub-02",
      "inc-stub-09",
      "inc-stub-06",
      "inc-stub-11",
      "inc-stub-04",
      "inc-stub-07",
      "inc-stub-03",
      "inc-stub-05",
      "inc-stub-08",
      "inc-stub-01",
    ]);
    expect(screen.getByRole("link", { name: "inc-stub-03" })).toHaveAttribute("href", "/incidents/inc-stub-03");
    expect(screen.getByRole("columnheader", { name: /Time/ })).toHaveAttribute("aria-sort", "descending");

    const first = items.find((item) => item.incident.incident_id === "inc-stub-01")!.incident;
    const time = within(rowOf("inc-stub-01")).getByText(formatLocalDateTime(first.first_event_at).slice(0, 16));
    expect(time).toHaveAttribute("title", `Last event: ${formatLocalDateTime(first.last_event_at)}`);
  });

  it("shows at most three entities, then +N, with the full list as a title", async () => {
    await renderStub();

    const cells = within(rowOf("inc-stub-01")).getAllByRole("cell");
    expect(cells[2]).toHaveTextContent("db-01, file-01, web-01 +6");
    expect(cells[2]).toHaveAttribute(
      "title",
      "Hosts: db-01, file-01, web-01; Users: svc-db, www-data; IPs: 10.10.1.21, 10.10.2.31, 10.10.5.5, 203.0.113.10",
    );
    expect(within(rowOf("inc-stub-03")).getAllByRole("cell")[2]).toHaveTextContent("ws-41, ws-42 · admin-shared +2");
    expect(within(rowOf("inc-stub-08")).getAllByRole("cell")[2]).toHaveTextContent(/^-$/);
  });

  it("shows Not scored and Not classified, labels, and Decide only on awaiting incidents", async () => {
    await renderStub();

    const notScored = within(rowOf("inc-stub-06"));
    expect(notScored.getByText("Not scored")).toBeInTheDocument();
    expect(notScored.getByText("Not classified")).toBeInTheDocument();
    expect(notScored.getByText("Not started")).toBeInTheDocument();
    expect(within(rowOf("inc-stub-01")).getByText("High 82")).toBeInTheDocument();
    expect(within(rowOf("inc-stub-05")).getByText("Failed")).toBeInTheDocument();

    const decide = screen.getAllByRole("link", { name: /^Decide on / });
    expect(decide.map((link) => link.getAttribute("href")).sort()).toEqual([
      "/incidents/inc-stub-01/decision",
      "/incidents/inc-stub-02/decision",
      "/incidents/inc-stub-03/decision",
      "/incidents/inc-stub-04/decision",
      "/incidents/inc-stub-12/decision",
    ]);
    expect(screen.queryAllByRole("button", { name: /simulat|isolate|block/i })).toHaveLength(0);
  });

  it("sorts by risk score with Not scored last in both directions", async () => {
    await renderStub();

    fireEvent.click(screen.getByRole("button", { name: /Risk/ }));
    expect(screen.getByRole("columnheader", { name: /Risk/ })).toHaveAttribute("aria-sort", "descending");
    expect(ids()).toEqual([
      "inc-stub-10",
      "inc-stub-01",
      "inc-stub-09",
      "inc-stub-07",
      "inc-stub-02",
      "inc-stub-12",
      "inc-stub-03",
      "inc-stub-05",
      "inc-stub-08",
      "inc-stub-04",
      "inc-stub-11",
      "inc-stub-06",
      "inc-stub-13",
    ]);
    expect(screen.getByTestId("location")).toHaveTextContent("?sort=risk");

    fireEvent.click(screen.getByRole("button", { name: /Risk/ }));
    expect(screen.getByRole("columnheader", { name: /Risk/ })).toHaveAttribute("aria-sort", "ascending");
    expect(ids()[0]).toBe("inc-stub-11");
    expect(ids().slice(-2)).toEqual(["inc-stub-06", "inc-stub-13"]);
  });

  it("filters by risk level and state, and Clear filters brings every row back", async () => {
    await renderStub();

    fireEvent.change(screen.getByLabelText("Risk level"), { target: { value: "high" } });
    expect(ids()).toEqual(["inc-stub-10", "inc-stub-02", "inc-stub-09", "inc-stub-07", "inc-stub-01"]);
    expect(screen.getByTestId("location")).toHaveTextContent("?level=high");

    fireEvent.change(screen.getByLabelText("State"), { target: { value: "closed" } });
    expect(screen.getByText("No incidents match these filters.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(ids()).toHaveLength(13);
    expect(screen.getByTestId("location")).toBeEmptyDOMElement();
  });

  it("filters by the Escalated state", async () => {
    await renderStub();

    fireEvent.change(screen.getByLabelText("State"), { target: { value: "escalated" } });
    expect(ids()).toEqual(["inc-stub-10"]);
    expect(within(rowOf("inc-stub-10")).getByText("Escalated")).toBeInTheDocument();
  });

  it("reads the filters and the sort from the URL", async () => {
    await renderStub("/incidents?level=high&state=awaiting_human_decision&sort=risk");

    expect(screen.getByLabelText("Risk level")).toHaveValue("high");
    expect(screen.getByLabelText("State")).toHaveValue("awaiting_human_decision");
    expect(ids()).toEqual(["inc-stub-01", "inc-stub-02"]);
  });

  it("shows no STUB banner when the answer has no X-ICD-Stub header", async () => {
    mockFetch().mockImplementation(async () => jsonResponse({ items }));
    renderAt();
    await screen.findByRole("table");

    expect(screen.queryByText(STUB_BANNER)).not.toBeInTheDocument();
  });

  it("shows loading, then the error block, and Retry loads again", async () => {
    const fetchMock = mockFetch();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    fetchMock.mockImplementation(async () => stubResponse({ items }));
    renderAt();

    expect(screen.getByText("Loading incidents…")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load incidents. Cannot reach the ICD API.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("shows the empty state with a link to Upload", async () => {
    mockFetch().mockImplementation(async () => jsonResponse({ items: [] }));
    renderAt();

    expect(await screen.findByText("No incidents yet. Upload a dataset to start.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload a dataset" })).toHaveAttribute("href", "/upload");
  });
});
