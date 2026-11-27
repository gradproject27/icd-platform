import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SIMULATED_LABEL } from "../labels";
import { StatusChip } from "./StatusChip";

describe("StatusChip", () => {
  it("marks response workflow states as simulated while keeping ordinary states unchanged", () => {
    render(
      <>
        <StatusChip status="new" />
        <StatusChip status="response_in_progress" />
      </>,
    );

    expect(screen.getByText("New")).toBeInTheDocument();
    expect(screen.getByText("Response in Progress")).toBeInTheDocument();
    expect(screen.getByText(SIMULATED_LABEL)).toBeInTheDocument();
  });
});
