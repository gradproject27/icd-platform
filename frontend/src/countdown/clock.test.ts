import { describe, expect, it } from "vitest";
import { formatRemaining, offsetFromPush, offsetFromRequest, parseIsoMs, remainingMs } from "./clock";

const T0 = Date.parse("2026-11-02T09:15:30.250Z");

describe("offsets", () => {
  it("offsetFromPush is server_time − receivedAt", () => {
    expect(offsetFromPush("2026-11-02T09:15:30.250Z", T0 - 90_000)).toBe(90_000);
    expect(offsetFromPush("2026-11-02T09:15:30.250Z", T0 + 1_500)).toBe(-1_500);
  });

  it("offsetFromRequest uses the midpoint of the request", () => {
    // Sent 200 ms before and received 200 ms after the server read its clock: offset 0.
    expect(offsetFromRequest("2026-11-02T09:15:30.250Z", T0 - 200, T0 + 200)).toBe(0);
    // Same request against a server clock 90 s ahead.
    expect(offsetFromRequest("2026-11-02T09:15:30.250Z", T0 - 90_200, T0 - 89_800)).toBe(90_000);
  });
});

describe("remainingMs", () => {
  const deadline = "2026-11-02T09:16:30.250Z"; // T0 + 60 s

  it("is deadline − (clientNow + offset)", () => {
    expect(remainingMs(deadline, 0, T0)).toBe(60_000);
    expect(remainingMs(deadline, 90_000, T0 - 90_000)).toBe(60_000);
    expect(remainingMs(deadline, 0, T0 + 42_500)).toBe(17_500);
  });

  it("never goes below 0", () => {
    expect(remainingMs(deadline, 0, T0 + 61_000)).toBe(0);
  });
});

describe("formatRemaining", () => {
  it.each([
    [60_000, "1:00"],
    [59_001, "1:00"],
    [59_000, "0:59"],
    [1, "0:01"],
    [0, "0:00"],
    [-5, "0:00"],
    [125_000, "2:05"],
  ])("%i ms -> %s", (ms, text) => {
    expect(formatRemaining(ms)).toBe(text);
  });

  it("throws on NaN", () => {
    expect(() => formatRemaining(Number.NaN)).toThrow(/NaN/);
  });
});

describe("invalid input", () => {
  it.each(["", "not a time", "2026-11-02 09:15:30", "2026-11-02T09:15:30", "2026-13-45T99:99:99Z"])(
    "rejects %j instead of producing NaN",
    (value) => {
      expect(() => parseIsoMs(value)).toThrow(/Invalid time/);
      expect(() => remainingMs(value, 0, T0)).toThrow(/Invalid deadline_at/);
      expect(() => offsetFromPush(value, T0)).toThrow(/Invalid server_time/);
    },
  );
});
