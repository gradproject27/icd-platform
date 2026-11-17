import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import example from "../../../docs/api/examples/notification-list.json";
import type { AuditRecord } from "../api/contracts";
import type { CurrentRole } from "../auth/useCurrentUser";
import { LAST_SEEN_KEY, NOTIFICATION_POLL_MS } from "../notifications/useNotifications";
import { jsonResponse, mockFetch } from "../test/fetch";
import { NotificationCenter, TOAST_MS } from "./NotificationCenter";

// Test data: the API example (a freeze_started notification for the SOC Analyst and the SOC
// Manager), and the same record with C5's other two reasons (spec T09, T11).
const FREEZE = example.items[0] as AuditRecord;
const INCIDENT = FREEZE.incident_id!;
const notification = (recordId: string, reason: string, recipients: string): AuditRecord => ({
  ...FREEZE,
  record_id: recordId,
  details: { reason, recipients },
});
const NO_MATCH = notification("aud-no-match", "no_match", "soc_manager");
const FAILED = notification("aud-failed", "simulated_action_failed", "soc_analyst,soc_manager");

const analyst: CurrentRole = { kind: "known", user: "analyst-dev", role: "soc_analyst" };

function serve(...answers: (AuditRecord[] | Response)[]) {
  const fetchMock = mockFetch();
  let call = 0;
  fetchMock.mockImplementation(async () => {
    const answer = answers[Math.min(call, answers.length - 1)]!;
    call += 1;
    return answer instanceof Response ? answer : jsonResponse({ items: answer });
  });
  return fetchMock;
}

function show(current: CurrentRole = analyst) {
  return render(
    <MemoryRouter>
      <NotificationCenter current={current} />
    </MemoryRouter>,
  );
}

const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const button = () => screen.getByRole("button", { name: /^Notifications/ });
const panel = () => screen.getByRole("region", { name: "Notifications" });

describe("NotificationCenter", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
  });

  it("shows the unread count and lists C5's notifications with their incident, reason and recipients", async () => {
    const fetchMock = serve([FREEZE]);
    show();
    await advance(0);

    expect(fetchMock).toHaveBeenCalledWith("/api/notifications?limit=50", expect.anything());
    expect(button()).toHaveTextContent("Notifications (1 unread)");
    fireEvent.click(button());
    const item = within(panel()).getByRole("listitem");
    expect(within(item).getByRole("link", { name: INCIDENT })).toHaveAttribute("href", `/incidents/${INCIDENT}`);
    expect(item).toHaveTextContent("Response window opened, host isolated (SIMULATED)");
    expect(item).toHaveTextContent("(to SOC Analyst, SOC Manager)");
  });

  it("reads again every 3 s and toasts a new notification, which closes by itself", async () => {
    const fetchMock = serve([FREEZE], [FAILED, FREEZE]);
    show();
    await advance(0);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    await advance(NOTIFICATION_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(button()).toHaveTextContent("Notifications (2 unread)");
    expect(screen.getByRole("status")).toHaveTextContent(`New notification: ${INCIDENT}: Simulated action failed: escalated`);

    await advance(TOAST_MS);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("shows each role only the notifications meant for it", async () => {
    serve([NO_MATCH, FREEZE]);
    const { unmount } = show();
    await advance(0);
    expect(button()).toHaveTextContent("Notifications (1 unread)");
    fireEvent.click(button());
    expect(panel()).not.toHaveTextContent("no scenario matched");
    unmount();

    serve([NO_MATCH, FREEZE]);
    show({ kind: "known", user: "manager-dev", role: "soc_manager" });
    await advance(0);
    expect(button()).toHaveTextContent("Notifications (2 unread)");

    serve([NO_MATCH, FREEZE]);
    show({ kind: "known", user: "eng-dev", role: "security_engineer" });
    await advance(0);
    expect(screen.getAllByRole("button", { name: /^Notifications/ })[1]).toHaveTextContent("Notifications (0 unread)");
  });

  it("shows every notification, and says why, while the role is unknown", async () => {
    serve([NO_MATCH, FREEZE]);
    show({ kind: "unknown" });
    await advance(0);
    expect(button()).toHaveTextContent("Notifications (2 unread)");
    fireEvent.click(button());
    expect(panel()).toHaveTextContent("Signed-in role unknown: showing all notifications.");
  });

  it("marks all as read and keeps the marker after a reload", async () => {
    serve([FREEZE]);
    const { unmount } = show();
    await advance(0);
    fireEvent.click(button());
    fireEvent.click(within(panel()).getByRole("button", { name: "Mark all as read" }));
    expect(button()).toHaveTextContent("Notifications (0 unread)");
    expect(window.localStorage.getItem(LAST_SEEN_KEY)).toBe(FREEZE.record_id);
    unmount();

    serve([FAILED, FREEZE]);
    show();
    await advance(0);
    expect(button()).toHaveTextContent("Notifications (1 unread)");
  });

  it("shows the empty state", async () => {
    serve([]);
    show();
    await advance(0);
    fireEvent.click(button());
    expect(panel()).toHaveTextContent("No notifications.");
  });

  it("says when the notifications cannot be read, and recovers on the next read", async () => {
    serve(jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500), [FREEZE]);
    show();
    await advance(0);
    expect(button()).toHaveTextContent("Notifications unavailable");
    fireEvent.click(button());
    expect(within(panel()).getByRole("alert")).toHaveTextContent("Could not read the notifications.");

    await advance(NOTIFICATION_POLL_MS);
    expect(button()).toHaveTextContent("Notifications (1 unread)");
    expect(within(panel()).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("works when the browser blocks storage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    serve([FREEZE]);
    show();
    await advance(0);
    fireEvent.click(button());
    fireEvent.click(within(panel()).getByRole("button", { name: "Mark all as read" }));
    expect(button()).toHaveTextContent("Notifications (0 unread)");
  });
});
