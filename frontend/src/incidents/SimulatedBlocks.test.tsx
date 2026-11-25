import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import example from "../../../docs/api/examples/containment-list.json";
import type { ContainmentList, SimulatedContainment } from "../api/proposed";
import { jsonResponse, mockFetch } from "../test/fetch";
import { BLOCKS_POLL_MS, SimulatedBlocks } from "./SimulatedBlocks";

// Test data: the API example, written from a real run of C5's engine on fixture incident A.
const LIST = example as ContainmentList;
const ACTIVE = LIST.items[0]!;
const ID = ACTIVE.incident_id;
const REVERTED: SimulatedContainment = { ...ACTIVE, status: "reverted", reverted_at: ACTIVE.ends_at };
const PATH = `/api/incidents/${ID}/containments`;

function serve(...answers: (ContainmentList | Response)[]) {
  const fetchMock = mockFetch();
  let call = 0;
  fetchMock.mockImplementation(async (url) => {
    if (String(url) !== PATH) return jsonResponse({ error: { code: "not_found", message: "x" } }, 404);
    const answer = answers[Math.min(call++, answers.length - 1)]!;
    return answer instanceof Response ? answer : jsonResponse(answer);
  });
  return fetchMock;
}

const flush = () => act(() => vi.advanceTimersByTimeAsync(0));

describe("SimulatedBlocks", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows an active block with its planned end and that it ends on its own", async () => {
    serve(LIST);
    render(<SimulatedBlocks incidentId={ID} refreshKey="" />);
    await flush();
    const box = screen.getByRole("region", { name: "Simulated IP blocks" });
    const [line] = within(box).getAllByRole("listitem");
    expect(line).toHaveTextContent(/Simulated IP block on 203\.0\.113\.10 until .* then it ends on its own/);
    expect(line).toHaveTextContent("first block of this IP");
    expect(line).toHaveTextContent("[SIMULATED]");
    expect(within(box).getByText(/Host isolation never ends on its own/)).toBeInTheDocument();
  });

  it("shows a repeat, an extension and an ended block", async () => {
    serve({ items: [{ ...REVERTED, offence: 2, extended: 1 }] });
    render(<SimulatedBlocks incidentId={ID} refreshKey="" />);
    await flush();
    const [line] = screen.getAllByRole("listitem");
    expect(line).toHaveTextContent(/ended at .*\(repeat 2 of this IP, extended 1×\)/);
  });

  it("shows nothing without a block, and nothing when the server cannot answer", async () => {
    serve({ items: [] });
    const { unmount } = render(<SimulatedBlocks incidentId={ID} refreshKey="" />);
    await flush();
    expect(screen.queryByRole("region", { name: "Simulated IP blocks" })).not.toBeInTheDocument();
    unmount();

    serve(jsonResponse({ error: { code: "internal_error", message: "Boom." } }, 500));
    render(<SimulatedBlocks incidentId={ID} refreshKey="" />);
    await flush();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reads again while a block is active, so the page shows when it ended", async () => {
    const fetchMock = serve(LIST, { items: [REVERTED] });
    render(<SimulatedBlocks incidentId={ID} refreshKey="" />);
    await flush();
    expect(screen.getByRole("listitem")).toHaveTextContent("until");
    await act(() => vi.advanceTimersByTimeAsync(BLOCKS_POLL_MS));
    expect(screen.getByRole("listitem")).toHaveTextContent("ended at");
    const reads = fetchMock.mock.calls.filter(([url]) => String(url) === PATH).length;
    await act(() => vi.advanceTimersByTimeAsync(BLOCKS_POLL_MS * 3));
    // Nothing active any more: no further reads.
    expect(fetchMock.mock.calls.filter(([url]) => String(url) === PATH).length).toBe(reads);
  });

  it("reads again when the decision changes", async () => {
    const fetchMock = serve({ items: [] }, LIST);
    const { rerender } = render(<SimulatedBlocks incidentId={ID} refreshKey="approved|" />);
    await flush();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    rerender(<SimulatedBlocks incidentId={ID} refreshKey="simulated_succeeded|" />);
    await flush();
    expect(screen.getByRole("region", { name: "Simulated IP blocks" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
