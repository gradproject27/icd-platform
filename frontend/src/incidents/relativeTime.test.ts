import { describe, expect, it } from "vitest";
import { formatRelativeTime } from "./relativeTime";

const NOW = Date.parse("2026-11-26T10:00:00Z");

describe("formatRelativeTime", () => {
  it("formats timestamps relative to the supplied clock", () => {
    expect(formatRelativeTime("2026-11-26T09:00:00Z", NOW)).toBe("1 hour ago");
    expect(formatRelativeTime("2026-11-26T11:00:00Z", NOW)).toBe("in 1 hour");
  });

  it("uses readable text for invalid timestamps", () => {
    expect(formatRelativeTime("not-a-date", NOW)).toBe("Time unavailable");
  });
});
