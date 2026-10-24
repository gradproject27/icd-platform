import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HEALTH_DEGRADED, HEALTH_OK, jsonResponse, mockFetch } from "../test/fetch";
import { HealthIndicator } from "./HealthIndicator";

describe("HealthIndicator", () => {
  it("shows API online on a 200 answer", async () => {
    mockFetch().mockResolvedValue(jsonResponse(HEALTH_OK));
    render(<HealthIndicator />);

    expect(screen.getByText("Checking…")).toBeInTheDocument();
    expect(await screen.findByText("API online")).toBeInTheDocument();
  });

  it("shows the degraded state on a 503 with the degraded body", async () => {
    mockFetch().mockResolvedValue(jsonResponse(HEALTH_DEGRADED, 503));
    render(<HealthIndicator />);

    expect(await screen.findByText("API degraded: database unavailable")).toBeInTheDocument();
  });

  it("shows API unavailable with the error kind as a tooltip when the API cannot be reached", async () => {
    mockFetch().mockRejectedValue(new TypeError("Failed to fetch"));
    render(<HealthIndicator />);

    const indicator = await screen.findByText("API unavailable");
    expect(indicator).toHaveAttribute("title", "Error: network");
    expect(indicator).toHaveAttribute("aria-live", "polite");
  });
});
