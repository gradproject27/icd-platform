import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import type { AuditRecord, IncidentStatus, ResponseAction, ScenarioId } from "../api/contracts";
import { getDecision, submitDecision } from "../api/decisions";
import { ApiError } from "../api/errors";
import { getAuditTrail, getIncident } from "../api/incidents";
import type { DecisionRecord, DecisionRequest, DecisionType, IncidentSummary } from "../api/proposed";
import { DECIDERS } from "../auth/roles";
import { useCurrentUser } from "../auth/useCurrentUser";
import { CountdownView } from "../components/Countdown";
import { PageState } from "../components/PageState";
import { formatLocalDateTime, formatRemaining } from "../countdown/clock";
import { useResponseWindow, type ResponseWindowView } from "../hooks/useResponseWindow";
import { IncidentHeader } from "../incidents/IncidentHeader";
import { STUB_BANNER } from "../incidents/format";
import { INCIDENT_STATUS_LABELS, SCENARIO_LABELS } from "../labels";

// Pending decision (wireframes.md 4.6; response-workflow-spec.md sections 7 to 10). The server owns
// the window and every rule: this page shows the countdown from the server's deadline_at, offers
// the three options of spec section 8 and "no response needed" (T16, S8-D10), asks for
// confirmation, and shows what the server answered. An escalated incident takes approve, select
// and no_action, never reject (T12, T16). The decision endpoints call C5's response engine
// (backend/app/api/incidents.py). Every response is SIMULATED.

const SCENARIOS = Object.keys(SCENARIO_LABELS) as ScenarioId[];
const COMMENT_MAX = 1_000;
/** How often the page reads the decision again while its simulated action is running. */
const ACTION_POLL_MS = 1_000;

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "not_found" }
  | { kind: "ready"; summary: IncidentSummary; stub: boolean; decision: DecisionRecord | null };

const simulated = <span className="simulated-badge">[SIMULATED]</span>;

const timeOfDay = (iso: string) => formatLocalDateTime(iso).slice(11);

function decisionLabel(decision: DecisionType, freeze: boolean): string {
  if (decision === "no_action") return "No response needed";
  if (decision === "approve") return "Approve recommended action (SIMULATED)";
  if (decision === "select") return "Select another scenario (SIMULATED)";
  return freeze ? "Reject and release simulated isolation (SIMULATED)" : "Reject the recommendation (SIMULATED)";
}

function actionStateText(action: ResponseAction): string {
  if (action.state === "simulated_succeeded") {
    return `Simulated, succeeded${action.executed_at ? ` at ${timeOfDay(action.executed_at)}` : ""}`;
  }
  if (action.state === "simulated_failed") {
    return `Simulated, failed${action.failure_reason ? `: ${action.failure_reason}` : ""}`;
  }
  if (action.state === "approved") return "Approved, running…";
  return "Proposed";
}

export function PendingDecisionPage() {
  const { incidentId = "" } = useParams();
  // key: a different incident starts from a fresh state, window read and socket.
  return <DecisionPanel key={incidentId} incidentId={incidentId} />;
}

function DecisionPanel({ incidentId }: { incidentId: string }) {
  const view = useResponseWindow(incidentId);
  const current = useCurrentUser();
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getIncident(incidentId, controller.signal), getDecision(incidentId, controller.signal)]).then(
      ([{ data, stub }, decision]) => setLoad({ kind: "ready", summary: data, stub, decision }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        // Only C1's not_found code means the incident does not exist. A bare 404 (the real API
        // before the incident endpoints exist) stays an error with Retry.
        if (error instanceof ApiError && error.kind === "http" && error.status === 404 && error.code === "not_found") {
          setLoad({ kind: "not_found" });
          return;
        }
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setLoad({ kind: "error", message: `Could not load incident ${incidentId}. ${reason}` });
      },
    );
    return () => controller.abort();
  }, [incidentId, attempt]);

  const setDecision = useCallback(
    (decision: DecisionRecord) =>
      setLoad((current) =>
        current.kind === "ready"
          ? {
              ...current,
              decision,
              summary: { ...current.summary, incident: { ...current.summary.incident, status: decision.incident_status } },
            }
          : current,
      ),
    [],
  );

  // A decision recorded elsewhere (another tab or analyst) closes the window: read it.
  const windowDecided = view.state === "decided";
  const hasDecision = load.kind === "ready" && load.decision !== null;
  useEffect(() => {
    if (!windowDecided || hasDecision) return;
    const controller = new AbortController();
    getDecision(incidentId, controller.signal).then(
      (decision) => {
        if (decision) setDecision(decision);
      },
      () => undefined,
    );
    return () => controller.abort();
  }, [windowDecided, hasDecision, incidentId, setDecision]);

  // While the simulated action runs, read the decision once a second until it has a result.
  const actionRunning = load.kind === "ready" && load.decision?.action?.state === "approved";
  useEffect(() => {
    if (!actionRunning) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      getDecision(incidentId, controller.signal).then(
        (decision) => {
          if (decision) setDecision(decision);
        },
        () => undefined,
      );
    }, ACTION_POLL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [actionRunning, incidentId, setDecision]);

  // Path B: the window expired with no analyst decision. The server selects a scenario and runs it
  // (simulated); GET /decision only holds analyst decisions, so read the incident and its audit
  // trail once a second until the system's outcome is there (C4-D6).
  const [systemOutcome, setSystemOutcome] = useState<SystemOutcome | null>(null);
  const expiredUndecided = view.state === "expired" && load.kind === "ready" && load.decision === null;
  const outcomeSettled = systemOutcome !== null && !UNSETTLED.includes(systemOutcome.status);
  useEffect(() => {
    if (!expiredUndecided || outcomeSettled) return;
    const controller = new AbortController();
    const read = () =>
      Promise.all([getIncident(incidentId, controller.signal), getAuditTrail(incidentId, controller.signal)]).then(
        ([{ data }, trail]) => {
          setSystemOutcome(systemOutcomeOf(data.incident.status ?? "new", trail));
          setLoad((current) => (current.kind === "ready" ? { ...current, summary: data } : current));
        },
        () => undefined,
      );
    void read();
    const timer = setInterval(() => void read(), ACTION_POLL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [expiredUndecided, outcomeSettled, incidentId]);

  const back = <Link to={`/incidents/${encodeURIComponent(incidentId)}`}>Back to incident</Link>;

  if (load.kind !== "ready") {
    return (
      <section>
        {back}
        <h1>Pending decision for incident {incidentId}</h1>
        {load.kind === "loading" ? (
          <PageState kind="loading" message="Loading incident…" />
        ) : load.kind === "not_found" ? (
          <>
            <PageState kind="error" message={`No incident with ID ${incidentId} exists.`} />
            <p>
              <Link to="/incidents">Go to the incident list</Link>
            </p>
          </>
        ) : (
          <PageState
            kind="error"
            message={load.message}
            onRetry={() => {
              setLoad({ kind: "loading" });
              setAttempt((value) => value + 1);
            }}
          />
        )}
      </section>
    );
  }

  const { summary, stub, decision } = load;
  // Only a role the API names hides the options; the server checks the role on every submit.
  const canDecide = current.kind !== "known" || DECIDERS.includes(current.role);
  const escalated = summary.incident.status === "escalated";

  return (
    <section>
      {back}
      <h1>Pending decision for incident {incidentId}</h1>
      {stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}
      <IncidentHeader summary={summary} />

      <CountdownView view={view} />

      {decision && <DecisionRecorded decision={decision} />}
      {expiredUndecided && <SystemSelection outcome={systemOutcome} />}
      {(!decision || escalated) && (
        <DecisionChoice
          incidentId={incidentId}
          summary={summary}
          view={view}
          canDecide={canDecide}
          onDecided={setDecision}
        />
      )}
    </section>
  );
}

/** Statuses in which the system's path after expiry has not finished yet. */
const UNSETTLED: IncidentStatus[] = ["awaiting_human_decision", "response_in_progress"];

interface SystemOutcome {
  status: IncidentStatus;
  /** C5's scenario.selected record of the expiry, if written. */
  selected: AuditRecord | null;
  /** C5's action.simulated record with trigger window_expiry, if written. */
  action: AuditRecord | null;
}

function systemOutcomeOf(status: IncidentStatus, trail: AuditRecord[]): SystemOutcome {
  const last = (match: (record: AuditRecord) => boolean) => [...trail].reverse().find(match) ?? null;
  return {
    status,
    selected: last((record) => record.event_type === "scenario.selected"),
    action: last((record) => record.event_type === "action.simulated" && record.details?.trigger === "window_expiry"),
  };
}

const detail = (record: AuditRecord | null, key: string): string | null => {
  const value = record?.details?.[key];
  return value === undefined || value === null ? null : String(value);
};

/** What the system did after the deadline, read from C5's audit trail (nothing is computed here). */
function SystemSelection({ outcome }: { outcome: SystemOutcome | null }) {
  if (outcome === null || (outcome.selected === null && UNSETTLED.includes(outcome.status))) {
    return (
      <p className="note" role="status">
        The window expired with no analyst decision. Waiting for the system&apos;s selection…
      </p>
    );
  }
  const scenarioId = (detail(outcome.selected, "scenario_id") ?? detail(outcome.action, "scenario_id")) as ScenarioId | null;
  const actionId = detail(outcome.action, "action_id");
  return (
    <section className="box decision-recorded" aria-labelledby="system-selection-heading">
      <h2 id="system-selection-heading">Selected by the system at the deadline</h2>
      <p>By system (no analyst decided within the window)</p>
      <p>
        Scenario:{" "}
        {scenarioId ? (
          <>
            {scenarioId} {SCENARIO_LABELS[scenarioId]} {simulated}
          </>
        ) : (
          "none: no catalogue scenario fits, so nothing was run and the incident goes to a human"
        )}
      </p>
      <p>Status: {INCIDENT_STATUS_LABELS[outcome.status]}</p>
      {outcome.action && (
        <p className="decision-action" role="status">
          Action {actionId ?? ""} (SIMULATED):{" "}
          {outcome.action.result === "success"
            ? "simulated, succeeded"
            : outcome.action.result === "failure"
              ? "simulated, failed"
              : outcome.action.result}
        </p>
      )}
    </section>
  );
}

function DecisionRecorded({ decision }: { decision: DecisionRecord }) {
  const { action } = decision;
  return (
    <section className="box decision-recorded" aria-labelledby="decision-recorded-heading">
      <h2 id="decision-recorded-heading">Decision recorded</h2>
      <p>
        By {decision.decided_by} at{" "}
        <time dateTime={decision.decided_at} title={decision.decided_at}>
          {formatLocalDateTime(decision.decided_at)}
        </time>
      </p>
      <p>Decision: {decisionLabel(decision.decision, decision.window_id !== null)}</p>
      <p>
        Scenario:{" "}
        {decision.scenario_id ? (
          <>
            {decision.scenario_id} {SCENARIO_LABELS[decision.scenario_id]} {simulated}
          </>
        ) : (
          "none"
        )}
      </p>
      <p>Comment: {decision.comment ?? "(none)"}</p>
      <p>Status: {INCIDENT_STATUS_LABELS[decision.incident_status]}</p>
      {action && (
        <p className="decision-action" role="status">
          Action {action.action_id} (SIMULATED): {actionStateText(action)}
        </p>
      )}
      {decision.decision === "reject" && decision.window_id !== null && (
        <p className="decision-action">Simulated isolation released. {simulated}</p>
      )}
    </section>
  );
}

interface DecisionChoiceProps {
  incidentId: string;
  summary: IncidentSummary;
  view: ResponseWindowView;
  canDecide: boolean;
  onDecided: (decision: DecisionRecord) => void;
}

function DecisionChoice({ incidentId, summary, view, canDecide, onDecided }: DecisionChoiceProps) {
  const [choice, setChoice] = useState<DecisionType | null>(null);
  const [otherScenario, setOtherScenario] = useState<ScenarioId | null>(null);
  const [comment, setComment] = useState("");
  const [step, setStep] = useState<"choose" | "confirm">("choose");
  const [submitting, setSubmitting] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [expiredByServer, setExpiredByServer] = useState(false);

  const status = summary.incident.status ?? "new";
  // An escalated incident's window is already over (T09, T11); its state does not close the options.
  const escalated = status === "escalated";
  const freeze = view.state === "open";
  const openWindow = view.window;
  const recommended: ScenarioId | null = freeze
    ? (openWindow?.recommended_scenario_id ?? null)
    : (summary.recommended_scenario_id ?? null);

  if (refusal) {
    return (
      <p className="decision-refusal" role="alert">
        {refusal}
      </p>
    );
  }
  if (view.state === "loading") return null;
  if (expiredByServer || (!escalated && view.state === "expired")) {
    return <p className="note">The options are closed: the response window has expired.</p>;
  }
  if (!escalated && view.state === "decided") return <p className="note">A decision has been recorded. Loading it…</p>;
  if (view.state === "error") {
    return <p className="note">The options are shown once the response window can be read.</p>;
  }
  if (status !== "awaiting_human_decision" && !escalated) {
    return (
      <p className="note">
        This incident is not awaiting a decision (status: {INCIDENT_STATUS_LABELS[status]}).
      </p>
    );
  }

  const scenario: ScenarioId | null =
    choice === "approve" ? recommended : choice === "select" ? otherScenario : null;
  const trimmedComment = comment.trim();
  const ready =
    choice === "reject" || (choice === "no_action" && trimmedComment !== "") || (choice !== null && scenario !== null);

  const body = (): DecisionRequest => ({
    decision: choice ?? "reject",
    scenario_id: scenario,
    window_id: freeze ? (openWindow?.window_id ?? null) : null,
    comment: trimmedComment === "" ? null : trimmedComment,
  });

  const submit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      onDecided(await submitDecision(incidentId, body()));
    } catch (error) {
      if (error instanceof ApiError && error.kind === "http" && error.status === 409 && error.code === "already_decided") {
        const recorded = await getDecision(incidentId).catch(() => null);
        if (recorded) onDecided(recorded);
        else setRefusal("Your decision was not recorded: a decision already exists for this incident.");
      } else if (error instanceof ApiError && error.kind === "http" && error.status === 409 && error.code === "window_open") {
        setSubmitError("Your decision was not recorded: a response window is open. Decide within the window.");
      } else if (error instanceof ApiError && error.kind === "http" && error.status === 409 && error.code === "not_awaiting_decision") {
        setRefusal("Your decision was not recorded: the incident is no longer awaiting a decision.");
      } else if (error instanceof ApiError && error.kind === "http" && error.status === 409) {
        const at = openWindow ? ` at ${timeOfDay(openWindow.deadline_at)}` : "";
        setRefusal(`Your decision was not recorded: the window expired${at}. The system path applies.`);
        setExpiredByServer(true);
      } else if (error instanceof ApiError && error.kind === "http" && error.status === 403) {
        setSubmitError("You are not allowed to make response decisions. Nothing was executed.");
      } else if (error instanceof ApiError && error.kind === "http" && error.status === 422) {
        setSubmitError(`Your decision was not recorded. ${error.message}`);
      } else {
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setSubmitError(`Could not submit the decision. ${reason}`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onReview = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (ready) setStep("confirm");
  };

  return (
    <>
      {freeze && <p className="isolation-line">Simulated isolation is active for this incident {simulated}</p>}

      <section className="box recommendation" aria-labelledby="recommendation-heading">
        <h2 id="recommendation-heading">Recommended response {simulated}</h2>
        {recommended ? (
          <>
            <p>
              <strong>{recommended}</strong> {SCENARIO_LABELS[recommended]}.
            </p>
            <p className="note">Chosen by the catalogue lookup, not by the AI.</p>
          </>
        ) : (
          <p>No catalogue scenario matches this incident.</p>
        )}
      </section>

      {!canDecide && <p className="note">Only a SOC Analyst can decide.</p>}

      {canDecide && submitError && (
        <p className="decision-refusal" role="alert">
          {submitError}
        </p>
      )}

      {!canDecide ? null : step === "choose" ? (
        <form className="decision-form" onSubmit={onReview}>
          <fieldset>
            <legend>Your decision</legend>
            <label className="option">
              <input
                type="radio"
                name="decision"
                value="approve"
                checked={choice === "approve"}
                disabled={!recommended}
                onChange={() => setChoice("approve")}
              />
              {recommended
                ? `Approve recommended action (${recommended}, SIMULATED)`
                : "Approve recommended action (SIMULATED)"}
              {!recommended && <span className="option__reason"> No recommended scenario</span>}
            </label>
            {!escalated && (
              <label className="option">
                <input
                  type="radio"
                  name="decision"
                  value="reject"
                  checked={choice === "reject"}
                  onChange={() => setChoice("reject")}
                />
                {decisionLabel("reject", freeze)}
              </label>
            )}
            <label className="option">
              <input
                type="radio"
                name="decision"
                value="select"
                checked={choice === "select"}
                onChange={() => setChoice("select")}
              />
              Select another scenario (SIMULATED):
            </label>
            <fieldset className="scenario-list" aria-label="Other scenario">
              {SCENARIOS.map((id) => (
                <label className="option option--nested" key={id}>
                  <input
                    type="radio"
                    name="scenario"
                    value={id}
                    checked={otherScenario === id}
                    onChange={() => {
                      setOtherScenario(id);
                      setChoice("select");
                    }}
                  />
                  {id} {SCENARIO_LABELS[id]} (SIMULATED)
                </label>
              ))}
            </fieldset>
            {!freeze && (
              <label className="option">
                <input
                  type="radio"
                  name="decision"
                  value="no_action"
                  checked={choice === "no_action"}
                  onChange={() => setChoice("no_action")}
                />
                {decisionLabel("no_action", freeze)}
                <span className="option__reason"> Nothing is executed. A comment is required.</span>
              </label>
            )}
          </fieldset>

          <label className="field">
            {choice === "no_action" ? "Comment (required for No response needed)" : "Comment (optional)"}
            <textarea
              value={comment}
              maxLength={COMMENT_MAX}
              rows={3}
              required={choice === "no_action"}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>

          <button type="submit" disabled={!ready}>
            Review decision
          </button>
        </form>
      ) : (
        <section className="box confirm" aria-labelledby="confirm-heading">
          <h2 id="confirm-heading">Confirm your decision</h2>
          <p>Incident {incidentId}</p>
          <p>Decision: {choice ? decisionLabel(choice, freeze) : ""}</p>
          <p>
            Scenario:{" "}
            {scenario ? (
              <>
                {scenario} {SCENARIO_LABELS[scenario]} {simulated}
              </>
            ) : (
              "none"
            )}
          </p>
          <p>Comment: {trimmedComment === "" ? "(none)" : trimmedComment}</p>
          <p>
            {choice === "no_action"
              ? "Nothing is executed. The decision is recorded and audited."
              : "No real system is changed. The action is simulated and audited."}
          </p>
          <div className="confirm__actions">
            {freeze && view.remainingMs !== null && (
              <span className="confirm__time">{formatRemaining(view.remainingMs)} left</span>
            )}
            <button type="button" onClick={() => setStep("choose")} disabled={submitting}>
              Back
            </button>
            <button type="button" onClick={() => void submit()} disabled={submitting}>
              {submitting ? "Submitting…" : "Submit decision"}
            </button>
          </div>
        </section>
      )}
    </>
  );
}
