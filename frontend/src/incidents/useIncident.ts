import { useEffect, useState } from "react";
import { ApiError } from "../api/errors";
import { getIncident } from "../api/incidents";
import type { IncidentSummary } from "../api/proposed";

export type IncidentLoad<T> =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "not_found" }
  | { kind: "ready"; summary: IncidentSummary; stub: boolean; extra: T };

/**
 * Reads one incident and, with it, whatever else the page needs (`more`). Only C1's not_found
 * code means the incident does not exist; any other failure is an error the page can retry.
 */
export function useIncident<T>(
  incidentId: string,
  more: (signal: AbortSignal) => Promise<T>,
): { load: IncidentLoad<T>; retry: () => void } {
  const [load, setLoad] = useState<IncidentLoad<T>>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getIncident(incidentId, controller.signal), more(controller.signal)]).then(
      ([{ data, stub }, extra]) => setLoad({ kind: "ready", summary: data, stub, extra }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404 && error.code === "not_found") {
          setLoad({ kind: "not_found" });
          return;
        }
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setLoad({ kind: "error", message: `Could not load incident ${incidentId}. ${reason}` });
      },
    );
    return () => controller.abort();
    // `more` is a fresh function on every render; the incident and the retry decide a reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidentId, attempt]);

  return {
    load,
    retry: () => {
      setLoad({ kind: "loading" });
      setAttempt((value) => value + 1);
    },
  };
}
