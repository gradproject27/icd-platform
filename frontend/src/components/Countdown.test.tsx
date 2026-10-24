import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket, mockWebSocket } from "../test/fakeWebSocket";
import { jsonResponse, mockFetch } from "../test/fetch";
import { Countdown } from "./Countdown";

const NOW = Date.parse("2026-11-02T09:15:00.000Z");
const iso = (ms: number) => new Date(ms).toISOString();

const openWindow = (serverNowMs = NOW) => ({
  incident_id: "inc-1",
  window_id: "win-0001",
  status: "open",
  started_at: iso(NOW),
  deadline_at: iso(NOW + 60_000),
  server_time: iso(serverNowMs),
  recommended_scenario_id: "S2",
});

/** Lets pending promises (fetch, state updates) settle, then moves the fake clock. */
const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const timer = () => screen.getByRole("timer");

describe("Countdown", () => {
  let fetchMock: ReturnType<typeof mockFetch>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    mockWebSocket();
    fetchMock = mockFetch();
  });

  it("shows 1:00, then 0:30 with the reminder after 30 s, computed from the server deadline", async () => {
    fetchMock.mockResolvedValue(jsonResponse(openWindow()));
    render(<Countdown incidentId="inc-1" />);
    await advance(0);

    expect(timer()).toHaveTextContent("1:00");
    expect(timer()).toHaveAttribute("aria-live", "off");
    expect(screen.getByText(/Deadline set by the server at/)).toBeInTheDocument();
    expect(screen.queryByText("30 seconds left")).not.toBeInTheDocument();

    await advance(30_000);
    expect(timer()).toHaveTextContent("0:30");
    expect(screen.getByText("30 seconds left")).toBeInTheDocument();
  });

  it("corrects for a server clock that is 90 s ahead of the browser", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ ...openWindow(NOW + 90_000), started_at: iso(NOW + 90_000), deadline_at: iso(NOW + 150_000) }),
    );
    render(<Countdown incidentId="inc-1" />);
    await advance(0);

    // Without the offset the browser would show 2:30.
    expect(timer()).toHaveTextContent("1:00");
  });

  it("connects to the response-window socket on the page's own origin", async () => {
    fetchMock.mockResolvedValue(jsonResponse(openWindow()));
    render(<Countdown incidentId="inc-1" />);
    await advance(0);

    expect(FakeWebSocket.latest().url).toBe(`ws://${window.location.host}/ws/response-windows?incident_id=inc-1`);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/response-windows/inc-1");
  });

  it("shows the expired text when the server pushes response_window.expired", async () => {
    fetchMock.mockResolvedValue(jsonResponse(openWindow()));
    render(<Countdown incidentId="inc-1" />);
    await advance(0);
    FakeWebSocket.latest().open();

    await advance(60_000);
    // At the deadline the client shows 0:00 but does not decide on its own that the window expired.
    expect(timer()).toHaveTextContent("0:00");

    act(() =>
      FakeWebSocket.latest().emit({
        type: "response_window.expired",
        incident_id: "inc-1",
        window_id: "win-0001",
        server_time: iso(NOW + 60_002),
      }),
    );
    expect(screen.getByText(/Window expired at/)).toHaveTextContent("The system selects a scenario (SIMULATED).");
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
  });

  it("shows Decision recorded on response_window.decided", async () => {
    fetchMock.mockResolvedValue(jsonResponse(openWindow()));
    render(<Countdown incidentId="inc-1" />);
    await advance(0);
    FakeWebSocket.latest().open();

    act(() =>
      FakeWebSocket.latest().emit({
        type: "response_window.decided",
        incident_id: "inc-1",
        window_id: "win-0001",
        server_time: iso(NOW + 5_000),
      }),
    );
    expect(screen.getByText("Decision recorded.")).toBeInTheDocument();
  });

  it("shows the no-window text on a 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "no response window" }, 404));
    render(<Countdown incidentId="inc-1" />);
    await advance(0);

    expect(screen.getByText("No response window. No automatic action will run.")).toBeInTheDocument();
    expect(screen.queryByRole("timer")).not.toBeInTheDocument();
  });

  it("keeps counting from the stored deadline while reconnecting, then reads the window again", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(openWindow(Date.now())));
    render(<Countdown incidentId="inc-1" />);
    await advance(0);
    FakeWebSocket.latest().open();

    act(() => FakeWebSocket.latest().drop());
    expect(screen.getByText(/Reconnecting… the time shown is still calculated/)).toBeInTheDocument();

    await advance(10_000);
    expect(timer()).toHaveTextContent("0:50");
    // Backoff 1 s, 2 s, 4 s, ... : the first retry was made after 1 s.
    expect(FakeWebSocket.instances.length).toBeGreaterThan(1);

    act(() => FakeWebSocket.latest().open());
    await advance(0);
    expect(screen.queryByText(/Reconnecting/)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(timer()).toHaveTextContent("0:50");
  });

  it("does not create or restart a window when it is mounted again (a page refresh)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(openWindow(Date.now())));
    const first = render(<Countdown incidentId="inc-1" />);
    await advance(0);
    await advance(20_000);
    expect(timer()).toHaveTextContent("0:40");
    first.unmount();

    render(<Countdown incidentId="inc-1" />);
    await advance(0);
    expect(timer()).toHaveTextContent("0:40");
    // Only GET reads: nothing on the client opens a window.
    expect(fetchMock.mock.calls.every(([, init]) => (init?.method ?? "GET") === "GET")).toBe(true);
  });
});
