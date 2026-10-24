import { useEffect, useState } from "react";
import { ApiError, type ApiErrorKind } from "../api/errors";
import { getHealth } from "../api/health";

export const HEALTH_POLL_INTERVAL_MS = 15_000;

export type HealthState =
  | { kind: "checking" }
  | { kind: "online" }
  | { kind: "degraded" }
  | { kind: "unavailable"; errorKind: ApiErrorKind | "unknown" };

/** Polls GET /health every 15 s and when the window regains focus. */
export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ kind: "checking" });

  useEffect(() => {
    let inFlight: AbortController | null = null;

    const check = async () => {
      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;
      try {
        const health = await getHealth(controller.signal);
        if (controller.signal.aborted) return;
        setState(health.status === "ok" ? { kind: "online" } : { kind: "degraded" });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({ kind: "unavailable", errorKind: error instanceof ApiError ? error.kind : "unknown" });
      }
    };

    const onFocus = () => void check();
    void check();
    const interval = setInterval(() => void check(), HEALTH_POLL_INTERVAL_MS);
    window.addEventListener("focus", onFocus);

    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      inFlight?.abort();
    };
  }, []);

  return state;
}
