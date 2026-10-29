import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import type { ResponseAction, ScenarioId } from "../api/contracts";
import { getDecision, submitDecision } from "../api/decisions";
import { ApiError } from "../api/errors";
import { getIncident } from "../api/incidents";
import type { DecisionRecord, DecisionRequest, DecisionType, IncidentSummary } from "../api/proposed";
import { CountdownView } from "../components/Countdown";
import { PageState } from "../components/PageState";
import { formatLocalDateTime, formatRemaining } from "../countdown/clock";
import { useResponseWindow, type ResponseWindowView } from "../hooks/useResponseWindow";
import { entitiesText, formatListTime, riskText, STUB_BANNER } from "../incidents/format";
import { INCIDENT_STATUS_LABELS, SCENARIO_LABELS } from "../labels";

// Pending decision (wireframes.md 4.6; response-workflow-spec.md sections 7 to 10). The server owns
// the window and every rule: this page shows the countdown from the server's deadline_at, offers
// the three options of spec section 8, asks for confirmation, and shows what the server answered.
// The decision endpoints are proposed for C5 (src/api/proposed.ts). Every response is SIMULATED.

const SCENARIOS = Object.keys(SCENARIO_LABELS) as ScenarioId[];
const COMMENT_MAX = 1_000;
/** How often the page reads the decision again while its simulated action is running. */
const ACTION_POLL_MS = 1_000;

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; summary: IncidentSummary; stub: boolean; decision: DecisionRecord | null };

const simulated = <span className="simulated-badge">[SIMULATED]</span>;

const timeOfDay = (iso: string) => formatLocalDateTime(iso).slice(11);

function decisionLabel(decision: DecisionType, freeze: boolean): string {
  if (decision === "approve") return "Approve recommended action";
  if (decision === "select") return "Select another scenario";
  return freeze ? "Reject and release simulated isolation" : "Reject the recommendation (SIMULATED)";
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
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getIncident(incidentId, controller.signal), getDecision(incidentId, controller.signal)]).then(
      ([{ data, stub }, decision]) => setLoad({ kind: "ready", summary: data, stub, decision }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
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

  const back = <Link to={`/incidents/${encodeURIComponent(incidentId)}`}>Back to incident</Link>;

  if (load.kind !== "ready") {
    return (
      <section>
        {back}
        <h1>Pending decision for incident {incidentId}</h1>
        {load.kind === "loading" ? (
          <PageState kind="loading" message="Loading incident…" />
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

      {decision ? (
        <DecisionRecorded decision={decision} />
      ) : (
        <DecisionChoice
          incidentId={incidentId}
          summary={summary}
          view={view}
          onDecided={setDecision}
        />
      )}
    </section>
  );
}

/** The compact incident header (decision D10): the panel shows it itself while the detail page is a shell. */
function IncidentHeader({ summary }: { summary: IncidentSummary }) {
  const { incident } = summary;
  const shownEntities = entitiesText(summary.entities);
  return (
    <dl className="incident-header" aria-label="Incident">
      <div>
        <dt>Incident</dt>
        <dd>{incident.incident_id}</dd>
      </div>
      <div>
        <dt>State</dt>
        <dd>{INCIDENT_STATUS_LABELS[incident.status ?? "new"]}</dd>
      </div>
      <div>
        <dt>Type</dt>
        <dd>{incident.incident_type ?? "Not classified"}</dd>
      </div>
      <div>
        <dt>Risk</dt>
        <dd>{riskText(incident)}</dd>
      </div>
      <div>
        <dt>First event</dt>
        <dd>
          <time dateTime={incident.first_event_at}>{formatListTime(incident.first_event_at)}</time>
        </dd>
      </div>
      <div>
        <dt>Last event</dt>
        <dd>
          <time dateTime={incident.last_event_at}>{formatListTime(incident.last_event_at)}</time>
        </dd>
      </div>
      <div>
        <dt>Entities</dt>
        <dd title={shownEntities.title}>{shownEntities.text}</dd>
      </div>
    </dl>
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
        <p className="decision-action">Simulated isolation released.</p>
      )}
    </section>
  );
}

interface DecisionChoiceProps {
  incidentId: string;
  summary: IncidentSummary;
  view: ResponseWindowView;
  onDecided: (decision: DecisionRecord) => void;
}

function DecisionChoice({ incidentId, summary, view, onDecided }: DecisionChoiceProps) {
  const [choice, setChoice] = useState<DecisionType | null>(null);
  const [otherScenario, setOtherScenario] = useState<ScenarioId | null>(null);
  const [comment, setComment] = useState("");
  const [step, setStep] = useState<"choose" | "confirm">("choose");
  const [submitting, setSubmitting] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [expiredByServer, setExpiredByServer] = useState(false);

  const status = summary.incident.status ?? "new";
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
  if (view.state === "expired" || expiredByServer) {
    return <p className="note">The options are closed: the response window has expired.</p>;
  }
  if (view.state === "decided") return <p className="note">A decision has been recorded. Loading it…</p>;
  if (view.state === "error") {
    return <p className="note">The options are shown once the response window can be read.</p>;
  }
  if (status !== "awaiting_human_decision") {
    return (
      <p className="note">
        This incident is not awaiting a decision (status: {INCIDENT_STATUS_LABELS[status]}).
      </p>
    );
  }

  const scenario: ScenarioId | null =
    choice === "approve" ? recommended : choice === "select" ? otherScenario : null;
  const ready = choice === "reject" || (choice !== null && scenario !== null);
  const trimmedComment = comment.trim();

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
      } else if (error instanceof ApiError && error.kind === "http" && error.status === 409) {
        const at = openWindow ? ` at ${timeOfDay(openWindow.deadline_at)}` : "";
        setRefusal(`Your decision was not recorded: the window expired${at}. The system path applies.`);
        setExpiredByServer(true);
      } else if (error instanceof ApiError && error.kind === "http" && error.status === 403) {
        setSubmitError("You are not allowed to make response decisions. Nothing was executed.");
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

      {submitError && (
        <p className="decision-refusal" role="alert">
          {submitError}
        </p>
      )}

      {step === "choose" ? (
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
          </fieldset>

          <label className="field">
            Comment (optional)
            <textarea
              value={comment}
              maxLength={COMMENT_MAX}
              rows={3}
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
          <p>No real system is changed. The action is simulated and audited.</p>
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
