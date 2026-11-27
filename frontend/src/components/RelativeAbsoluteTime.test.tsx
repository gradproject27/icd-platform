import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RelativeAbsoluteTime } from "./RelativeAbsoluteTime";

describe("RelativeAbsoluteTime", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows a relative time alongside an accessible absolute timestamp", () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-11-26T10:00:00Z"));
    const iso = "2026-11-26T09:00:00Z";
    const { container } = render(<RelativeAbsoluteTime iso={iso} />);
    const time = container.querySelector("time");

    expect(time).toHaveAttribute("dateTime", iso);
    expect(screen.getByText("1 hour ago")).toBeInTheDocument();
    expect(time).toHaveAttribute("aria-label", expect.stringContaining("1 hour ago"));
  });
});
