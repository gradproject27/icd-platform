import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import recent from "../../../docs/api/examples/recent-decision-list.json";
import catalogue from "../../../docs/api/examples/scenario-catalogue.json";
import { jsonResponse, mockFetch } from "../test/fetch";
import { RecentDecisions, ScenarioImpactLine, ScenarioMetaTable } from "./ScenarioMeta";

// Test data: the API examples, written from real runs of the backend routes.

function serve(answers: Record<string, unknown>) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    const key = Object.keys(answers).find((prefix) => path.startsWith(prefix));
    if (!key) return jsonResponse({ error: { code: "not_found", message: "x" } }, 404);
    const answer = answers[key];
    return answer instanceof Response ? answer : jsonResponse(answer);
  });
  return fetchMock;
}

const renderIn = (node: React.ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>);

describe("ScenarioMetaTable", () => {
  it("shows each scenario's impact, whether the system may select it and how it is reverted", async () => {
    serve({ "/api/scenarios": catalogue });
    renderIn(<ScenarioMetaTable />);
    const box = await screen.findByRole("region", { name: "Impact and revert of each scenario" });
    const s2 = within(box).getByRole("rowheader", { name: "S2" }).closest("tr")!;
    expect(s2).toHaveTextContent("High");
    expect(s2).toHaveTextContent(/ends on its own/);
    const s4 = within(box).getByRole("rowheader", { name: "S4" }).closest("tr")!;
    expect(s4).toHaveTextContent("No, analyst only");
    expect(within(box).getByText(/Display only \(scenario-meta-v1\)/)).toBeInTheDocument();
  });

  it("shows nothing when the server cannot answer", async () => {
    const fetchMock = serve({});
    renderIn(<ScenarioMetaTable />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalled();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});

describe("ScenarioImpactLine", () => {
  it("names the recommended scenario's impact and revert", async () => {
    serve({ "/api/scenarios": catalogue });
    renderIn(<ScenarioImpactLine scenarioId="S3" />);
    expect(await screen.findByText(/Impact: High\. Only an analyst ends the isolation/)).toBeInTheDocument();
  });
});

describe("RecentDecisions", () => {
  it("lists analyst decisions and system selections, newest first", async () => {
    serve({ "/api/decisions/recent": recent });
    renderIn(<RecentDecisions />);
    const box = await screen.findByRole("region", { name: "Decisions in the last 72 hours" });
    const rows = within(box).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Selected by the system at the deadline");
    expect(rows[0]).toHaveTextContent("System");
    expect(rows[1]).toHaveTextContent('Approved ("Checked the timeline")');
    expect(rows[1]).toHaveTextContent("analyst-dev");
    expect(within(rows[1]!).getByRole("link")).toHaveAttribute("href", expect.stringMatching(/\/audit$/));
  });

  it("says when there was no decision", async () => {
    serve({ "/api/decisions/recent": { ...recent, items: [] } });
    renderIn(<RecentDecisions />);
    expect(await screen.findByText("No decision in the last 72 hours.")).toBeInTheDocument();
  });
});
