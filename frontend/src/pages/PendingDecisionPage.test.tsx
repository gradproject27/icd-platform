import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import containments from "../../../docs/api/examples/containment-list.json";
import stubData from "../../dev/stub-data/incidents.json";
import type { ResponseAction, UserRole } from "../api/contracts";
import type { DecisionRecord, IncidentSummary } from "../api/proposed";
import { FakeWebSocket, mockWebSocket } from "../test/fakeWebSocket";
import { jsonResponse, mockFetch } from "../test/fetch";
import { PendingDecisionPage } from "./PendingDecisionPage";

// Test data: the committed stub incidents. inc-stub-01 has a freeze (open window, S2 recommended),
// inc-stub-03 waits without a window (S2 recommended), inc-stub-04 has no matching scenario,
// inc-stub-07 is resolved.

const NOW = Date.parse("2026-11-02T09:15:00.000Z");
const iso = (ms: number) => new Date(ms).toISOString();

const summaries = new Map(
  stubData.items.map(({ incident, entities, recommended_scenario_id }) => [
    incident.incident_id,
    { incident, entities, recommended_scenario_id } as IncidentSummary,
  ]),
);

const openWindow = (incidentId: string) => ({
  incident_id: incidentId,
  window_id: "win-0001",
  status: "open",
  started_at: iso(NOW),
  deadline_at: iso(NOW + 60_000),
  server_time: iso(NOW),
  recommended_scenario_id: "S2",
});

const record = (fields: Partial<DecisionRecord>): DecisionRecord => ({
  incident_id: "inc-stub-01",
  window_id: "win-0001",
  decision: "approve",
  scenario_id: "S2",
  comment: null,
  decided_by: "stub-analyst",
  decided_at: iso(NOW + 5_000),
  incident_status: "response_in_progress",
  action: null,
  ...fields,
});

const action = (fields: Partial<ResponseAction>): ResponseAction => ({
  schema_version: "1.0",
  action_id: "act-stub-inc-stub-01-1",
  incident_id: "inc-stub-01",
  window_id: "win-0001",
  scenario_id: "S2",
  state: "approved",
  simulated: true,
  trigger: "analyst_decision",
  target: { host: "db-01", ip: "10.10.1.21", account: "svc-db" },
  proposed_at: iso(NOW),
  decided_by: "stub-analyst",
  decided_at: iso(NOW + 5_000),
  executed_at: null,
  failure_reason: null,
  ...fields,
});

interface Api {
  window?: unknown;
  decision?: DecisionRecord | null | (() => DecisionRecord | null);
  submit?: () => Response;
  /** The role GET /me answers with; without it /me is a 404 and the role is unknown. */
  me?: UserRole;
  /** The incident status GET /incidents/{id} answers with, read on every call. */
  status?: () => string;
  /** GET /incidents/{id}/audit items, read on every call. */
  audit?: () => unknown[];
}

function serve(incidentId: string, api: Api = {}) {
  const fetchMock = mockFetch();
  fetchMock.mockImplementation(async (url, init) => {
    const path = String(url);
    if (path === `/api/incidents/${incidentId}`) {
      if (!summaries.has(incidentId)) {
        return jsonResponse({ error: { code: "not_found", message: `No incident with ID ${incidentId} exists.` } }, 404);
      }
      const summary = summaries.get(incidentId)!;
      const shown = api.status ? { ...summary, incident: { ...summary.incident, status: api.status() } } : summary;
      return new Response(JSON.stringify(shown), {
        status: 200,
        headers: { "Content-Type": "application/json", "X-ICD-Stub": "1" },
      });
    }
    if (path === `/api/incidents/${incidentId}/decision`) {
      const decision = typeof api.decision === "function" ? api.decision() : api.decision;
      return decision
        ? jsonResponse(decision)
        : jsonResponse({ error: { code: "not_found", message: "No decision." } }, 404);
    }
    if (path === `/api/response-windows/${incidentId}`) {
      return api.window ? jsonResponse(api.window) : jsonResponse({ detail: "no response window" }, 404);
    }
    if (path === `/api/incidents/${incidentId}/audit` && api.audit) return jsonResponse({ items: api.audit() });
    if (path === "/api/me" && api.me) return jsonResponse({ user: "dev", role: api.me });
    if (path === `/api/incidents/${incidentId}/decisions` && init?.method === "POST") {
      return api.submit ? api.submit() : jsonResponse(record({ incident_id: incidentId }), 201);
    }
    return jsonResponse({ error: { code: "not_found", message: "Not in this test." } }, 404);
  });
  return fetchMock;
}

function renderPage(incidentId: string) {
  return render(
    <MemoryRouter initialEntries={[`/incidents/${incidentId}/decision`]}>
      <Routes>
        <Route path="/incidents/:incidentId/decision" element={<PendingDecisionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const option = (name: string | RegExp) => screen.getByRole("radio", { name });
const header = () => screen.getByText("State").closest("dl")!;

function postedBody(fetchMock: ReturnType<typeof mockFetch>) {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  return JSON.parse(String(call?.[1]?.body)) as unknown;
}

describe("PendingDecisionPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    mockWebSocket();
  });

  it("shows the freeze: countdown, simulated isolation, recommendation and the three options", async () => {
    serve("inc-stub-01", { window: openWindow("inc-stub-01") });
    renderPage("inc-stub-01");
    await advance(0);

    expect(screen.getByRole("heading", { name: "Pending decision for incident inc-stub-01" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("STUB DATA");
    // The compact header (D10), with the list's formats; the risk is the stub's placeholder.
    expect(header()).toHaveTextContent("Incidentinc-stub-01");
    expect(header()).toHaveTextContent("StateAwaiting Human Decision");
    expect(header()).toHaveTextContent("TypeBackdoors");
    expect(header()).toHaveTextContent("RiskHigh 82");
    expect(header()).toHaveTextContent(/First event\d{4}-\d\d-\d\d \d\d:\d\d/);
    expect(header()).toHaveTextContent(/Last event\d{4}-\d\d-\d\d \d\d:\d\d/);
    expect(header()).toHaveTextContent("Entitiesdb-01, file-01, web-01 +6");
    expect(screen.getByRole("timer")).toHaveTextContent("1:00");
    expect(screen.getByText(/Simulated isolation is active for this incident/)).toHaveTextContent("[SIMULATED]");

    const recommendation = screen.getByRole("region", { name: /Recommended response/ });
    expect(recommendation).toHaveTextContent("[SIMULATED]");
    expect(recommendation).toHaveTextContent("S2 Isolate the host and block the source IP.");
    expect(recommendation).toHaveTextContent("Chosen by the catalogue lookup, not by the AI.");

    const labels = within(screen.getByRole("group", { name: "Your decision" }))
      .getAllByRole("radio")
      .map((radio) => radio.closest("label")?.textContent);
    expect(labels).toEqual([
      "Approve recommended action (S2, SIMULATED)",
      "Reject and release simulated isolation (SIMULATED)",
      "Select another scenario (SIMULATED):",
      "S1 Keep the host isolated and flag it for investigation (SIMULATED)",
      "S2 Isolate the host and block the source IP (SIMULATED)",
      "S3 Isolate the host and disable the involved account (SIMULATED)",
      "S4 Release isolation and raise monitoring (SIMULATED)",
    ]);
    expect(screen.getByRole("button", { name: "Review decision" })).toBeDisabled();
  });

  it("approves through the confirmation step and shows the recorded decision", async () => {
    const fetchMock = serve("inc-stub-01", { window: openWindow("inc-stub-01") });
    renderPage("inc-stub-01");
    await advance(0);

    fireEvent.click(option("Approve recommended action (S2, SIMULATED)"));
    fireEvent.click(screen.getByRole("button", { name: "Review decision" }));
    await advance(10_000);

    const confirm = screen.getByRole("region", { name: "Confirm your decision" });
    expect(confirm).toHaveTextContent("Incident inc-stub-01");
    expect(confirm).toHaveTextContent("Decision: Approve recommended action (SIMULATED)");
    expect(confirm).toHaveTextContent("Scenario: S2 Isolate the host and block the source IP [SIMULATED]");
    expect(confirm).toHaveTextContent("Comment: (none)");
    expect(confirm).toHaveTextContent("No real system is changed. The action is simulated and audited.");
    expect(confirm).toHaveTextContent("0:50 left");
    const buttons = within(confirm).getAllByRole("button").map((button) => button.textContent);
    expect(buttons).toEqual(["Back", "Submit decision"]);

    fireEvent.click(within(confirm).getByRole("button", { name: "Submit decision" }));
    await advance(0);

    expect(postedBody(fetchMock)).toEqual({ decision: "approve", scenario_id: "S2", window_id: "win-0001", comment: null });
    const recorded = screen.getByRole("region", { name: "Decision recorded" });
    expect(recorded).toHaveTextContent("By stub-analyst at");
    expect(recorded).toHaveTextContent("Decision: Approve recommended action (SIMULATED)");
    expect(recorded).toHaveTextContent("Scenario: S2 Isolate the host and block the source IP [SIMULATED]");
    expect(recorded).toHaveTextContent("Status: Response in Progress");
    // The page header follows the new state too, not only the recorded-decision box.
    expect(header()).toHaveTextContent("StateResponse in Progress");
    expect(screen.queryByRole("group", { name: "Your decision" })).not.toBeInTheDocument();
  });

  it("goes back from the confirmation step with the choice kept", async () => {
    serve("inc-stub-01", { window: openWindow("inc-stub-01") });
    renderPage("inc-stub-01");
    await advance(0);

    fireEvent.click(option("Reject and release simulated isolation (SIMULATED)"));
    fireEvent.click(screen.getByRole("button", { name: "Review decision" }));
    expect(screen.getByRole("region", { name: "Confirm your decision" })).toHaveTextContent(
      "Decision: Reject and release simulated isolation (SIMULATED)",
    );
    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(option("Reject and release simulated isolation (SIMULATED)")).toBeChecked();
  });

  it("without a window: no countdown, no isolation, 'Reject the recommendation', and select with a comment", async () => {
    const fetchMock = serve("inc-stub-03", {
      submit: () =>
        jsonResponse(
          record({
            incident_id: "inc-stub-03",
            window_id: null,
            decision: "select",
            scenario_id: "S4",
            comment: "Monitor only",
          }),
          201,
        ),
    });
    renderPage("inc-stub-03");
    await advance(0);

    expect(screen.getByText("No response window. No automatic action will run.")).toBeInTheDocument();
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
    expect(screen.queryByText(/Simulated isolation is active/)).not.toBeInTheDocument();
    expect(option("Reject the recommendation (SIMULATED)")).toBeInTheDocument();
    expect(header()).toHaveTextContent("RiskMedium 55");

    fireEvent.click(option("S4 Release isolation and raise monitoring (SIMULATED)"));
    expect(option("Select another scenario (SIMULATED):")).toBeChecked();
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: "  Monitor only  " } });
    fireEvent.click(screen.getByRole("button", { name: "Review decision" }));
    expect(screen.getByRole("region", { name: "Confirm your decision" })).toHaveTextContent("Comment: Monitor only");
    expect(screen.getByRole("region", { name: "Confirm your decision" })).not.toHaveTextContent("left");
    fireEvent.click(screen.getByRole("button", { name: "Submit decision" }));
    await advance(0);

    expect(postedBody(fetchMock)).toEqual({ decision: "select", scenario_id: "S4", window_id: null, comment: "Monitor only" });
    const recorded = screen.getByRole("region", { name: "Decision recorded" });
    expect(recorded).toHaveTextContent("Decision: Select another scenario (SIMULATED)");
    expect(recorded).toHaveTextContent("Comment: Monitor only");
  });

  it("disables Approve with the reason when no catalogue scenario matches", async () => {
    serve("inc-stub-04");
    renderPage("inc-stub-04");
    await advance(0);

    expect(screen.getByRole("region", { name: /Recommended response/ })).toHaveTextContent(
      "No catalogue scenario matches this incident.",
    );
    expect(option(/Approve recommended action \(SIMULATED\)/)).toBeDisabled();
    expect(screen.getByText("No recommended scenario")).toBeInTheDocument();
    expect(option("Reject the recommendation (SIMULATED)")).toBeEnabled();
    expect(option("S1 Keep the host isolated and flag it for investigation (SIMULATED)")).toBeEnabled();
  });

  it("reports a decision refused because the window expired (409) and closes the options", async () => {
    serve("inc-stub-01", {
      window: openWindow("inc-stub-01"),
      submit: () => jsonResponse({ error: { code: "window_expired", message: "The response window expired." } }, 409),
    });
    renderPage("inc-stub-01");
    await advance(0);

    fireEvent.click(option("Approve recommended action (S2, SIMULATED)"));
    fireEvent.click(screen.getByRole("button", { name: "Review decision" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit decision" }));
    await advance(0);

    const deadline = new Date(NOW + 60_000);
    const pad = (n: number) => String(n).padStart(2, "0");
    const at = `${pad(deadline.getHours())}:${pad(deadline.getMinutes())}:${pad(deadline.getSeconds())}`;
    expect(screen.getByRole("alert")).toHaveTextContent(
      `Your decision was not recorded: the window expired at ${at}. The system path applies.`,
    );
    expect(screen.queryByRole("button", { name: /Submit decision|Review decision/ })).not.toBeInTheDocument();
  });

  it("reports a decision the user may not make (403) and nothing executed", async () => {
    serve("inc-stub-03", {
      submit: () => jsonResponse({ error: { code: "forbidden", message: "Not allowed." } }, 403),
    });
    renderPage("inc-stub-03");
    await advance(0);

    fireEvent.click(option("Reject the recommendation (SIMULATED)"));
    fireEvent.click(screen.getByRole("button", { name: "Review decision" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit decision" }));
    await advance(0);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "You are not allowed to make response decisions. Nothing was executed.",
    );
    expect(screen.queryByRole("region", { name: "Decision recorded" })).not.toBeInTheDocument();
  });

  it("shows a decision already recorded on load, without the options", async () => {
    serve("inc-stub-01", {
      window: { ...openWindow("inc-stub-01"), status: "decided" },
      decision: record({ decision: "reject", scenario_id: null, comment: "False positive", incident_status: "awaiting_human_decision" }),
    });
    renderPage("inc-stub-01");
    await advance(0);

    const recorded = screen.getByRole("region", { name: "Decision recorded" });
    expect(recorded).toHaveTextContent("Decision: Reject and release simulated isolation (SIMULATED)");
    expect(recorded).toHaveTextContent("Scenario: none");
    expect(recorded).toHaveTextContent("Comment: False positive");
    expect(recorded).toHaveTextContent("Simulated isolation released. [SIMULATED]");
    expect(recorded).not.toHaveTextContent("Action ");
    expect(screen.queryByRole("group", { name: "Your decision" })).not.toBeInTheDocument();
  });

  it("does not claim an isolation release for a reject without a window", async () => {
    serve("inc-stub-03", {
      decision: record({
        incident_id: "inc-stub-03",
        window_id: null,
        decision: "reject",
        scenario_id: null,
        incident_status: "awaiting_human_decision",
      }),
    });
    renderPage("inc-stub-03");
    await advance(0);

    const recorded = screen.getByRole("region", { name: "Decision recorded" });
    expect(recorded).toHaveTextContent("Decision: Reject the recommendation (SIMULATED)");
    expect(recorded).not.toHaveTextContent("isolation released");
  });

  it("follows the simulated action once a second until it succeeds, and the state to Resolved", async () => {
    let current = record({ action: action({}) });
    const fetchMock = serve("inc-stub-01", {
      window: { ...openWindow("inc-stub-01"), status: "decided" },
      decision: () => current,
    });
    renderPage("inc-stub-01");
    await advance(0);

    const recorded = screen.getByRole("region", { name: "Decision recorded" });
    expect(recorded).toHaveTextContent("Action act-stub-inc-stub-01-1 (SIMULATED): Approved, running…");
    const decisionReads = () => fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/decision")).length;
    const before = decisionReads();
    await advance(1_000);
    expect(decisionReads()).toBe(before + 1);

    const executedAt = NOW + 8_000;
    current = record({
      incident_status: "resolved",
      action: action({ state: "simulated_succeeded", executed_at: iso(executedAt) }),
    });
    await advance(1_000);
    const pad = (n: number) => String(n).padStart(2, "0");
    const at = new Date(executedAt);
    expect(recorded).toHaveTextContent(
      `Action act-stub-inc-stub-01-1 (SIMULATED): Simulated, succeeded at ${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`,
    );
    expect(header()).toHaveTextContent("StateResolved");

    const after = decisionReads();
    await advance(3_000);
    expect(decisionReads()).toBe(after);
  });

  it("shows why a simulated action failed", async () => {
    serve("inc-stub-01", {
      window: { ...openWindow("inc-stub-01"), status: "decided" },
      decision: record({ action: action({ state: "simulated_failed", failure_reason: "Simulator unavailable" }) }),
    });
    renderPage("inc-stub-01");
    await advance(0);

    expect(screen.getByRole("region", { name: "Decision recorded" })).toHaveTextContent(
      "Action act-stub-inc-stub-01-1 (SIMULATED): Simulated, failed: Simulator unavailable",
    );
  });

  it("closes the options when the server pushes response_window.expired", async () => {
    serve("inc-stub-01", { window: openWindow("inc-stub-01") });
    renderPage("inc-stub-01");
    await advance(0);
    expect(screen.getByRole("group", { name: "Your decision" })).toBeInTheDocument();

    act(() => {
      FakeWebSocket.latest().open();
      FakeWebSocket.latest().emit({
        type: "response_window.expired",
        incident_id: "inc-stub-01",
        window_id: "win-0001",
        server_time: iso(NOW + 60_000),
      });
    });

    expect(screen.queryByRole("group", { name: "Your decision" })).not.toBeInTheDocument();
    expect(screen.getByText("The options are closed: the response window has expired.")).toBeInTheDocument();
  });

  it("shows loading, then the error block when the API cannot be reached, and Retry loads again", async () => {
    const fetchMock = serve("inc-stub-03");
    const answer = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url) === "/api/incidents/inc-stub-03") throw new TypeError("Failed to fetch");
      return answer(url, init);
    });
    renderPage("inc-stub-03");

    expect(screen.getByText("Loading incident…")).toBeInTheDocument();
    await advance(0);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load incident inc-stub-03. Cannot reach the ICD API.");

    fetchMock.mockImplementation(answer);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByText("Loading incident…")).toBeInTheDocument();
    await advance(0);
    expect(screen.getByRole("group", { name: "Your decision" })).toBeInTheDocument();
  });

  it("shows not found, without Retry, for an unknown incident (404 not_found)", async () => {
    serve("inc-nope");
    renderPage("inc-nope");
    await advance(0);

    expect(screen.getByRole("alert")).toHaveTextContent("No incident with ID inc-nope exists.");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the incident list" })).toHaveAttribute("href", "/incidents");
  });

  it("keeps a 404 without C1's code (endpoint not built yet) as an error with Retry", async () => {
    const fetchMock = serve("inc-stub-03");
    const answer = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, init) =>
      String(url) === "/api/incidents/inc-stub-03" ? jsonResponse({ detail: "Not Found" }, 404) : answer(url, init),
    );
    renderPage("inc-stub-03");
    await advance(0);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not load incident inc-stub-03. The ICD API answered with HTTP 404.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText(/No incident with ID/)).not.toBeInTheDocument();
  });

  it("shows the incident's simulated IP blocks with their planned end (P2)", async () => {
    const fetchMock = serve("inc-stub-03");
    const answer = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, init) =>
      String(url) === "/api/incidents/inc-stub-03/containments" ? jsonResponse(containments) : answer(url, init),
    );
    renderPage("inc-stub-03");
    await advance(0);

    const box = screen.getByRole("region", { name: "Simulated IP blocks" });
    expect(box).toHaveTextContent(/203\.0\.113\.10 until .* then it ends on its own/);
    expect(screen.getByRole("group", { name: "Your decision" })).toBeInTheDocument();
  });

  it("reports a submit that cannot reach the API, keeps the choice, and records nothing", async () => {
    serve("inc-stub-03", {
      submit: () => {
        throw new TypeError("Failed to fetch");
      },
    });
    renderPage("inc-stub-03");
    await advance(0);

    fireEvent.click(option("Reject the recommendation (SIMULATED)"));
    fireEvent.click(screen.getByRole("button", { name: "Review decision" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit decision" }));
    await advance(0);

    expect(screen.getByRole("alert")).toHaveTextContent("Could not submit the decision. Cannot reach the ICD API.");
    expect(screen.getByRole("button", { name: "Submit decision" })).toBeEnabled();
    expect(screen.queryByRole("region", { name: "Decision recorded" })).not.toBeInTheDocument();
  });

  it("offers no options on an incident that is not awaiting a decision", async () => {
    serve("inc-stub-07");
    renderPage("inc-stub-07");
    await advance(0);

    expect(screen.getByText("This incident is not awaiting a decision (status: Resolved).")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Your decision" })).not.toBeInTheDocument();
  });

  // ---- S8-D10: no response needed, escalated incidents, read-only roles ------------------------

  it("records 'No response needed' without a window, only with a comment", async () => {
    const fetchMock = serve("inc-stub-03", {
      submit: () =>
        jsonResponse(
          record({
            incident_id: "inc-stub-03",
            window_id: null,
            decision: "no_action",
            scenario_id: null,
            comment: "Benign scan",
            incident_status: "resolved",
          }),
          201,
        ),
    });
    renderPage("inc-stub-03");
    await advance(0);

    fireEvent.click(option(/^No response needed/));
    const review = screen.getByRole("button", { name: "Review decision" });
    expect(review).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Comment (required for No response needed)"), { target: { value: "   " } });
    expect(review).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Comment (required for No response needed)"), { target: { value: " Benign scan " } });
    fireEvent.click(review);

    const confirm = screen.getByRole("region", { name: "Confirm your decision" });
    expect(confirm).toHaveTextContent("Decision: No response needed");
    expect(confirm).toHaveTextContent("Scenario: none");
    expect(confirm).toHaveTextContent("Nothing is executed. The decision is recorded and audited.");
    fireEvent.click(screen.getByRole("button", { name: "Submit decision" }));
    await advance(0);

    expect(postedBody(fetchMock)).toEqual({ decision: "no_action", scenario_id: null, window_id: null, comment: "Benign scan" });
    const recorded = screen.getByRole("region", { name: "Decision recorded" });
    expect(recorded).toHaveTextContent("Decision: No response needed");
    expect(recorded).toHaveTextContent("Status: Resolved");
  });

  it("does not offer 'No response needed' while a response window is open", async () => {
    serve("inc-stub-01", { window: openWindow("inc-stub-01") });
    renderPage("inc-stub-01");
    await advance(0);

    expect(option("Approve recommended action (S2, SIMULATED)")).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /^No response needed/ })).not.toBeInTheDocument();
  });

  it("offers select and 'No response needed' on an escalated incident, but not reject", async () => {
    serve("inc-stub-10", { window: { ...openWindow("inc-stub-10"), status: "expired" } });
    renderPage("inc-stub-10");
    await advance(0);

    expect(screen.queryByText(/The options are closed/)).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Reject/ })).not.toBeInTheDocument();
    expect(option("Select another scenario (SIMULATED):")).toBeEnabled();
    expect(option(/^No response needed/)).toBeEnabled();
  });

  it("shows the options again under a recorded decision once the incident is escalated (T12)", async () => {
    serve("inc-stub-10", {
      window: { ...openWindow("inc-stub-10"), status: "decided" },
      decision: record({ incident_id: "inc-stub-10", incident_status: "escalated" }),
    });
    renderPage("inc-stub-10");
    await advance(0);

    expect(screen.getByRole("region", { name: "Decision recorded" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Your decision" })).toBeInTheDocument();
  });

  it("explains a 422 from the server and records nothing", async () => {
    serve("inc-stub-03", {
      submit: () => jsonResponse({ error: { code: "validation_error", message: "No_action needs a comment." } }, 422),
    });
    renderPage("inc-stub-03");
    await advance(0);

    fireEvent.click(option(/^No response needed/));
    fireEvent.change(screen.getByLabelText("Comment (required for No response needed)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Review decision" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit decision" }));
    await advance(0);

    expect(screen.getByRole("alert")).toHaveTextContent("Your decision was not recorded. No_action needs a comment.");
    expect(screen.queryByRole("region", { name: "Decision recorded" })).not.toBeInTheDocument();
  });

  it.each<UserRole>(["soc_manager", "security_engineer", "system_administrator"])(
    "is read-only for the %s: recommendation shown, no options",
    async (role) => {
      serve("inc-stub-03", { me: role });
      renderPage("inc-stub-03");
      await advance(0);

      expect(screen.getByRole("region", { name: /Recommended response/ })).toBeInTheDocument();
      expect(screen.getByText("Only a SOC Analyst can decide.")).toBeInTheDocument();
      expect(screen.queryByRole("group", { name: "Your decision" })).not.toBeInTheDocument();
    },
  );

  it("offers the options to the SOC Analyst", async () => {
    serve("inc-stub-03", { me: "soc_analyst" });
    renderPage("inc-stub-03");
    await advance(0);

    expect(screen.getByRole("group", { name: "Your decision" })).toBeInTheDocument();
    expect(screen.queryByText("Only a SOC Analyst can decide.")).not.toBeInTheDocument();
  });

  it("path B: after the deadline, shows the scenario the system selected and its simulated result", async () => {
    let status = "awaiting_human_decision";
    let audit: unknown[] = [];
    const rec = (record_id: string, event_type: string, details: Record<string, unknown>) => ({
      schema_version: "1.0",
      record_id,
      occurred_at: iso(NOW + 60_500),
      incident_id: "inc-stub-01",
      actor: "system",
      event_type,
      result: "success",
      simulated: event_type === "action.simulated",
      details,
    });
    serve("inc-stub-01", { window: openWindow("inc-stub-01"), status: () => status, audit: () => audit });
    renderPage("inc-stub-01");
    await advance(0);
    act(() => {
      FakeWebSocket.latest().open();
      FakeWebSocket.latest().emit({
        type: "response_window.expired",
        incident_id: "inc-stub-01",
        window_id: "win-0001",
        server_time: iso(NOW + 60_000),
      });
    });
    await advance(0);
    expect(screen.getByText(/Waiting for the system's selection/)).toBeInTheDocument();

    status = "resolved";
    audit = [
      rec("aud-1", "scenario.selected", { scenario_id: "S2", window_id: "win-0001" }),
      rec("aud-2", "action.simulated", { action_id: "act-9", scenario_id: "S2", trigger: "window_expiry", label: "SIMULATED" }),
    ];
    await advance(1_000);
    const box = screen.getByRole("region", { name: "Selected by the system at the deadline" });
    expect(box).toHaveTextContent("S2");
    expect(box).toHaveTextContent("[SIMULATED]");
    expect(box).toHaveTextContent("Status: Resolved");
    expect(within(box).getByRole("status")).toHaveTextContent("Action act-9 (SIMULATED): simulated, succeeded");
    expect(within(header()).getByText("Resolved")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Your decision" })).not.toBeInTheDocument();
  });
});
