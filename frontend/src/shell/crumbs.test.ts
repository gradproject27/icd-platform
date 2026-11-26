import { describe, expect, it } from "vitest";
import { breadcrumbsFor } from "./crumbs";

describe("breadcrumbsFor", () => {
  it("has none on /", () => {
    expect(breadcrumbsFor("/")).toEqual([]);
  });

  it.each([
    ["/incidents", "Incidents"],
    ["/review", "Review"],
    ["/entities", "Entities"],
    ["/upload", "Upload"],
    ["/configuration", "Configuration"],
    ["/overview", "Overview"],
  ])("names the top page %s", (path, label) => {
    expect(breadcrumbsFor(path)).toEqual([{ label }]);
  });

  it("links the list from an incident and shows the ID in monospace", () => {
    expect(breadcrumbsFor("/incidents/inc-1")).toEqual([
      { label: "Incidents", to: "/incidents" },
      { label: "inc-1", mono: true },
    ]);
  });

  it("names an incident sub-page like the detail page's links", () => {
    expect(breadcrumbsFor("/incidents/inc-1/decision")).toEqual([
      { label: "Incidents", to: "/incidents" },
      { label: "inc-1", to: "/incidents/inc-1", mono: true },
      { label: "Pending decision" },
    ]);
    expect(breadcrumbsFor("/incidents/inc-1/graph").at(-1)).toEqual({ label: "Entity graph" });
    expect(breadcrumbsFor("/incidents/inc-1/audit").at(-1)).toEqual({ label: "Audit trail" });
  });

  it("decodes the ID for display and encodes it again in the link", () => {
    const crumbs = breadcrumbsFor("/incidents/inc%20a%2F1/report");
    expect(crumbs[1]).toEqual({ label: "inc a/1", to: "/incidents/inc%20a%2F1", mono: true });
  });

  it("keeps a malformed escape as typed", () => {
    expect(breadcrumbsFor("/incidents/inc-%E0")[1]?.label).toBe("inc-%E0");
  });

  it.each([
    "/nope",
    "/incidents/inc-1/nope",
    "/review/x",
    "/incidents/inc-1/report/x",
    "/constructor",
    "/incidents/inc-1/toString",
  ])(
    "says Page not found for %s",
    (path) => {
      expect(breadcrumbsFor(path)).toEqual([{ label: "Page not found" }]);
    },
  );
});
