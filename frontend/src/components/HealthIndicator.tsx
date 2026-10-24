import { useHealth, type HealthState } from "../hooks/useHealth";

const LABELS: Record<HealthState["kind"], string> = {
  checking: "Checking…",
  online: "API online",
  degraded: "API degraded: database unavailable",
  unavailable: "API unavailable",
};

/** Backend status from GET /health. The text carries the meaning; the colour is extra. */
export function HealthIndicator() {
  const state = useHealth();
  return (
    <span
      className={`health health--${state.kind}`}
      aria-live="polite"
      title={state.kind === "unavailable" ? `Error: ${state.errorKind}` : undefined}
    >
      <span className="health__dot" aria-hidden="true" />
      {LABELS[state.kind]}
    </span>
  );
}
