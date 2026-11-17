import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import stubData from "../../dev/stub-data/incidents.json";
import type { UserRole } from "../api/contracts";
import { jsonResponse, mockFetch } from "../test/fetch";
import { ReviewQueuePage } from "./ReviewQueuePage";

// Test data: the committed stub incidents. Awaiting a decision: inc-stub-03 and inc-stub-12 are
// Medium, inc-stub-02 is High at 0.62, inc-stub-04 is Low, inc-stub-01 is High at 0.86 (it has a
// window, so it is not in a group). inc-stub-10 is escalated.

const LIST = { items: stubData.items };
const NOT_SIGNED_IN = { error: { code: "not_authenticated", message: "No signed-in user." } };

function serve({ list, role }: { list?: Response; role?: UserRole | null } = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url) => {
    const path = String(url);
    if (path === "/api/incidents") return list ?? jsonResponse(LIST);
    if (path === "/api/me") return role ? jsonResponse({ user: "dev", role }) : jsonResponse(NOT_SIGNED_IN, 401);
    return jsonResponse({ error: { code: "not_found", message: "Not in this test." } }, 404);
  });
  return fetchMock;
}

function show() {
  render(
    <MemoryRouter>
      <ReviewQueuePage />
    </MemoryRouter>,
  );
}

const group = (name: RegExp) => screen.getByRole("region", { name });
const ids = (region: HTMLElement) =>
  within(region)
    .queryAllByRole("link", { name: /^inc-/ })
    .map((link) => link.textContent);

describe("ReviewQueuePage", () => {
  it("groups the incidents waiting with no timer by the spec's table, oldest first", async () => {
    serve({ role: "soc_analyst" });
    show();
    await screen.findByRole("heading", { name: /Medium risk/ });

    expect(ids(group(/Medium risk \(2\)/))).toEqual(["inc-stub-03", "inc-stub-12"]);
    expect(ids(group(/High risk, confidence below 0.75 \(1\)/))).toEqual(["inc-stub-02"]);
    expect(ids(group(/Low risk \(1\)/))).toEqual(["inc-stub-04"]);
    expect(screen.getByText(/1 more incident awaits a decision/)).toBeInTheDocument();

    const medium = group(/Medium risk/);
    expect(within(medium).getByRole("link", { name: "Review inc-stub-03" })).toHaveAttribute(
      "href",
      "/incidents/inc-stub-03/decision",
    );
    expect(within(medium).getAllByText("S2 (SIMULATED)").length).toBeGreaterThan(0);
    expect(within(group(/Low risk/)).getByText("No matching scenario")).toBeInTheDocument();
    expect(screen.queryByText(/Read-only/)).not.toBeInTheDocument();
  });

  it.each<UserRole>(["soc_analyst", "soc_manager"])("shows the Escalated group to the %s", async (role) => {
    serve({ role });
    show();
    expect(ids(await screen.findByRole("region", { name: /Escalated \(1\)/ }))).toEqual(["inc-stub-10"]);
  });

  it.each<UserRole | null>(["security_engineer", "system_administrator", null])(
    "hides the Escalated group from %s",
    async (role) => {
      serve({ role });
      show();
      await screen.findByRole("heading", { name: /Medium risk/ });
      expect(screen.queryByRole("region", { name: /Escalated/ })).not.toBeInTheDocument();
      expect(screen.getByText(/Escalated incidents are shown to the SOC Analyst and SOC Manager only/)).toBeInTheDocument();
    },
  );

  it("says the queue is read-only for a role that cannot decide", async () => {
    serve({ role: "soc_manager" });
    show();
    expect(await screen.findByText("Read-only: only a SOC Analyst can decide.")).toBeInTheDocument();
  });

  it("shows the empty state when nothing waits", async () => {
    serve({ role: "soc_analyst", list: jsonResponse({ items: [] }) });
    show();
    expect(await screen.findByText("Nothing waits for review.")).toBeInTheDocument();
  });

  it("shows the error block with Retry when the list cannot be read", async () => {
    serve({ role: "soc_analyst", list: jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500) });
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the review queue. Boom.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
