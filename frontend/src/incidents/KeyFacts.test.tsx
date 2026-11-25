import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import example from "../../../docs/api/examples/incident-key-facts.json";
import type { IncidentKeyFacts } from "../api/proposed";
import { KeyFacts } from "./KeyFacts";

// Test data: the API example, written from a real run of key_facts on C3's fixture incident A.
const FACTS = example as IncidentKeyFacts;
const ID = FACTS.incident_id;

function show(facts: IncidentKeyFacts | null) {
  render(
    <MemoryRouter>
      <KeyFacts incidentId={ID} facts={facts} />
    </MemoryRouter>,
  );
  return screen.getByRole("region", { name: "Key facts" });
}

const row = (box: HTMLElement, name: string) => within(box).getByRole("rowheader", { name }).closest("tr")!;

describe("KeyFacts", () => {
  it("says the facts come from code, not the AI, and that context events are not counted", () => {
    const box = show(FACTS);
    expect(within(box).getByText(/Computed by code from the 8 flagged events, not by the AI/)).toBeInTheDocument();
    expect(within(box).getByText(/The 3 context events are not counted/)).toBeInTheDocument();
    expect(within(box).getByText(/response configuration response-v1/)).toBeInTheDocument();
  });

  it("shows where and when the incident started", () => {
    const box = show(FACTS);
    expect(within(box).getByText("web-01", { selector: "dd" })).toBeInTheDocument();
    expect(within(box).getByText("203.0.113.10", { selector: "dd" })).toBeInTheDocument();
    expect(within(box).getByText(/\(fx-002\)/)).toBeInTheDocument();
    expect(within(box).getByText(/\(fx-013\)/)).toBeInTheDocument();
  });

  it("lists each value with its count and links its cited events to the incident timeline", () => {
    const box = show(FACTS);
    const attackTypes = row(box, "Attack types (dataset labels)");
    expect(within(attackTypes).getAllByRole("listitem").map((li) => li.querySelector("strong")!.textContent)).toEqual([
      "Reconnaissance",
      "Exploits",
      "Backdoors",
    ]);
    const external = row(box, "External IPs");
    expect(within(external).getByText("203.0.113.10")).toBeInTheDocument();
    expect(within(external).getByText(/× 4/)).toBeInTheDocument();
    expect(within(external).getByRole("link", { name: "fx-008" })).toHaveAttribute(
      "href",
      `/incidents/${ID}#event-fx-008`,
    );
  });

  it("shows the ATT&CK tactics from the table, with the table version and MITRE's notice", () => {
    const box = show(FACTS);
    const tactics = row(box, "MITRE ATT&CK tactics (from the table, not the AI)");
    expect(within(tactics).getAllByRole("listitem").map((li) => li.querySelector("strong")!.textContent)).toEqual([
      "TA0043 Reconnaissance",
      "TA0001 Initial Access",
      "TA0003 Persistence",
      "TA0011 Command and Control",
    ]);
    expect(within(box).getByText(/reviewed table tactics-v1/)).toBeInTheDocument();
    expect(within(box).getByText(/© The MITRE Corporation/)).toBeInTheDocument();
  });

  it("says None for an empty list and marks cut lists", () => {
    const box = show({ ...FACTS, accounts: [], truncated: true });
    expect(within(row(box, "Accounts")).getByText("None")).toBeInTheDocument();
    expect(within(box).getByText("Some lists are cut at 20 values.")).toBeInTheDocument();
  });

  it("marks an item that cites fewer events than it counts", () => {
    const [first] = FACTS.hosts;
    const box = show({ ...FACTS, hosts: [{ ...first!, event_count: 40 }] });
    expect(within(row(box, "Hosts")).getByText(/…\)/)).toBeInTheDocument();
  });

  it("says plainly when the server sent no key facts", () => {
    const box = show(null);
    expect(within(box).getByText("Key facts are not available from this server.")).toBeInTheDocument();
  });
});
