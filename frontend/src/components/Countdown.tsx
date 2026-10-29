import type { ReactNode } from "react";
import { formatLocalDateTime, formatRemaining } from "../countdown/clock";
import { useResponseWindow, type ResponseWindowView } from "../hooks/useResponseWindow";
import { PageState } from "./PageState";

/**
 * The response-window countdown (T1-11). It only displays the server's deadline_at; it never
 * starts its own 60-second timer and cannot create, restart or extend a window (NFR-P-09).
 */
export function Countdown({ incidentId }: { incidentId: string }) {
  return <CountdownView view={useResponseWindow(incidentId)} />;
}

/** The countdown for a window the caller already follows, so a page needs only one socket. */
export function CountdownView({ view }: { view: ResponseWindowView }) {
  if (view.state === "loading") return <PageState kind="loading" message="Loading response window…" />;
  if (view.state === "error") {
    return <PageState kind="error" message={`Could not load the response window. ${view.error ?? ""}`.trim()} />;
  }

  const deadline = view.window ? (
    <time dateTime={view.window.deadline_at} title={view.window.deadline_at}>
      {formatLocalDateTime(view.window.deadline_at)}
    </time>
  ) : null;

  let status: ReactNode;
  switch (view.state) {
    case "none":
      status = "No response window. No automatic action will run.";
      break;
    case "decided":
      status = "Decision recorded.";
      break;
    case "expired":
      status = <>Window expired at {deadline}. The system selects a scenario (SIMULATED).</>;
      break;
    case "open":
      status = view.reminder ? "30 seconds left" : null;
      break;
  }

  return (
    <section className={`countdown${view.reminder ? " countdown--reminder" : ""}`} aria-labelledby="countdown-heading">
      <h2 id="countdown-heading">Response window</h2>
      {view.state === "open" && view.remainingMs !== null && (
        <>
          {/* Off: a screen reader must not read every second. State changes use the region below. */}
          <p className="countdown__time" role="timer" aria-live="off">
            {formatRemaining(view.remainingMs)}
          </p>
          <p className="countdown__deadline">Deadline set by the server at {deadline}</p>
        </>
      )}
      <div className="countdown__status" aria-live="polite">
        {view.connection === "reconnecting" && (
          <p className="countdown__notice">Reconnecting… the time shown is still calculated from the server deadline.</p>
        )}
        {status && <p>{status}</p>}
      </div>
    </section>
  );
}
