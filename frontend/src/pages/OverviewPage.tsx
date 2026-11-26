import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import type { AuditRecord } from "../api/contracts";
import { ApiError } from "../api/errors";
import { getEntityRisk, getRecentDecisions, listIncidents } from "../api/incidents";
import { getNotifications } from "../api/notifications";
import type { EntityRiskList, IncidentSummary, RecentDecisionList } from "../api/proposed";
import { Countdown } from "../components/Countdown";
import { PageState } from "../components/PageState";
import { RiskChip, RiskShape } from "../components/RiskChip";
import { formatLocalDateTime } from "../countdown/clock";
import { entitiesText, STUB_BANNER } from "../incidents/format";
import {
  DECISION_LABELS,
  INCIDENT_STATUS_LABELS,
  NOTIFICATION_REASON_LABELS,
  RISK_LEVEL_LABELS,
} from "../labels";
import { BarTable, StackedBar, TimeColumns, type BarRow } from "../overview/charts";
import {
  awaitingDecision,
  countByLevel,
  countByStatus,
  LEVEL_ORDER,
  perTimeBucket,
  STATUS_ORDER,
  type LevelKey,
} from "../overview/metrics";

// Overview (SOC UI phase 3): a summary built only from endpoints the dashboard already reads.
// Every number links to the incident list filtered the same way. Nothing here scores, ranks or
// decides: counts come from GET /incidents, risk from the risk engine as given.

/** Live countdowns on the decision list (decision D17); the rest are listed with a link. */
export const LIVE_COUNTDOWNS = 5;
/** Window of the recent-decision panel. */
export const RECENT_DECISION_HOURS = 24;
const TOP_ENTITIES = 5;
const LATEST_NOTIFICATIONS = 5;

type Load<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

/** One GET for a panel, with its own loading/error state and a retry. */
function usePanel<T>(read: (signal: AbortSignal) => Promise<T>, what: string) {
  const [load, setLoad] = useState<Load<T>>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    read(controller.signal).then(
      (data) => setLoad({ kind: "ready", data }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setLoad({ kind: "error", message: `Could not load ${what}. ${reason}` });
      },
    );
    return () => controller.abort();
    // `read` and `what` are module-level constants for each panel; only a retry reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);
  const retry = () => {
    setLoad({ kind: "loading" });
    setAttempt((value) => value + 1);
  };
  return { load, retry };
}

const readIncidents = (signal: AbortSignal) => listIncidents(signal);
const readEntities = (signal: AbortSignal) => getEntityRisk(undefined, signal);
const readDecisions = (signal: AbortSignal) => getRecentDecisions(RECENT_DECISION_HOURS, signal);
const readNotifications = (signal: AbortSignal) => getNotifications(signal);

function Panel({ id, title, action, children }: { id: string; title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel" aria-labelledby={id}>
      <header className="panel__header">
        <h2 id={id}>{title}</h2>
        {action}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}

function PanelState<T>({ load, retry, loading, render }: {
  load: Load<T>;
  retry: () => void;
  loading: string;
  render: (data: T) => ReactNode;
}) {
  if (load.kind === "loading") return <PageState kind="loading" message={loading} />;
  if (load.kind === "error") return <PageState kind="error" message={load.message} onRetry={retry} />;
  return <>{render(load.data)}</>;
}

const LEVEL_LABEL: Record<LevelKey, string> = { ...RISK_LEVEL_LABELS, none: "Not scored" };

function Kpi({ label, value, note, to }: { label: string; value: number; note: string; to: string }) {
  return (
    <Link className="kpi" to={to}>
      <span className="kpi__label">{label}</span>
      {" "}
      <span className="kpi__value">{value}</span>
      {" "}
      <span className="kpi__note">{note}</span>
    </Link>
  );
}

function IncidentSummaryPanels({ items }: { items: IncidentSummary[] }) {
  const levels = useMemo(() => countByLevel(items), [items]);
  const statuses = useMemo(() => countByStatus(items), [items]);
  const series = useMemo(() => perTimeBucket(items), [items]);

  const levelRows: BarRow[] = LEVEL_ORDER.map((level) => ({
    key: level,
    label: LEVEL_LABEL[level],
    count: levels[level],
    to: `/incidents?level=${level}`,
    tone: `risk-${level}`,
    shape: <RiskShape level={level} />,
  }));
  const statusRows: BarRow[] = STATUS_ORDER.map((status) => ({
    key: status,
    label: INCIDENT_STATUS_LABELS[status],
    count: statuses[status],
    to: `/incidents?state=${status}`,
    tone: `status-${status}`,
  }));

  return (
    <>
      <div className="kpi-row">
        <Kpi label="Incidents" value={items.length} note="All correlated incidents" to="/incidents" />
        <Kpi
          label="Awaiting human decision [SIMULATED]"
          value={statuses.awaiting_human_decision}
          note="Open the queue filtered by this state"
          to="/incidents?state=awaiting_human_decision"
        />
        <Kpi label="High risk" value={levels.high} note="Level High from the risk engine" to="/incidents?level=high" />
        <Kpi label="Escalated" value={statuses.escalated} note="Incidents in the state Escalated" to="/incidents?state=escalated" />
      </div>

      <div className="overview-grid">
        <Panel id="ov-by-level" title="Incidents by risk level">
          <BarTable caption="Incidents by risk level" rows={levelRows} />
          <p className="panel__note">Levels and scores come from the risk engine; this page only counts them.</p>
        </Panel>
        <Panel id="ov-by-state" title="Incidents by state">
          <StackedBar label="Incidents by state" rows={statusRows} />
        </Panel>
        <Panel id="ov-over-time" title="Incidents over time (dataset time)">
          {series.buckets.length === 0 ? (
            <p className="muted">No incident has a first-event time.</p>
          ) : (
            <TimeColumns series={series} what="Incidents by first event" />
          )}
          <p className="panel__note">Counted by each incident's first event, in the dataset's own time.</p>
        </Panel>
      </div>
    </>
  );
}

function DecisionQueue({ items }: { items: IncidentSummary[] }) {
  const waiting = awaitingDecision(items);
  if (waiting.length === 0) return <p className="muted">No incident is awaiting a human decision.</p>;
  const live = waiting.slice(0, LIVE_COUNTDOWNS);
  const rest = waiting.slice(LIVE_COUNTDOWNS);
  return (
    <>
      <ol className="decision-queue">
        {live.map((item) => {
          const id = item.incident.incident_id;
          const entities = entitiesText(item.entities);
          return (
            <li key={id} className="decision-queue__item">
              <div className="decision-queue__head">
                <Link className="mono" to={`/incidents/${encodeURIComponent(id)}/decision`}>
                  {id}
                </Link>
                <RiskChip risk={item.incident.risk} />
                <span className="muted">{item.incident.incident_type ?? "Not classified"}</span>
                <span className="muted" title={entities.title}>
                  {entities.text}
                </span>
              </div>
              <Countdown incidentId={id} />
            </li>
          );
        })}
      </ol>
      {rest.length > 0 && (
        <p className="panel__note">
          {rest.length} more awaiting a decision without a live countdown here:{" "}
          {rest.map((item, index) => (
            <span key={item.incident.incident_id}>
              {index > 0 && ", "}
              <Link className="mono" to={`/incidents/${encodeURIComponent(item.incident.incident_id)}/decision`}>
                {item.incident.incident_id}
              </Link>
            </span>
          ))}
          .
        </p>
      )}
    </>
  );
}

function EntityPanel({ data }: { data: EntityRiskList }) {
  const top = data.items.slice(0, TOP_ENTITIES);
  if (top.length === 0) return <p className="muted">No entity has a risk roll-up yet.</p>;
  return (
    <table className="table table--compact">
      <thead>
        <tr>
          <th scope="col">Entity</th>
          <th scope="col">Risk</th>
          <th scope="col">Incidents</th>
        </tr>
      </thead>
      <tbody>
        {top.map((item) => (
          <tr key={item.entity}>
            <th scope="row" className="mono">
              {item.entity}
            </th>
            <td>
              <RiskChip risk={item} />
            </td>
            <td className="num">{item.incident_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DecisionsPanel({ data }: { data: RecentDecisionList }) {
  if (data.items.length === 0) return <p className="muted">No decision in the last {data.hours} hours.</p>;
  return (
    <ol className="feed">
      {data.items.slice(0, 8).map((item) => (
        <li key={item.record_id} className="feed__item">
          <time className="feed__time" dateTime={item.occurred_at} title={item.occurred_at}>
            {formatLocalDateTime(item.occurred_at).slice(0, 16)}
          </time>
          <span>
            <Link className="mono" to={`/incidents/${encodeURIComponent(item.incident_id)}/audit`}>
              {item.incident_id}
            </Link>{" "}
            {DECISION_LABELS[item.decision] ?? item.decision}
            {item.scenario_id && (
              <>
                {" "}
                {item.scenario_id}
              </>
            )}{" "}
            <span className="simulated-badge">[SIMULATED]</span>{" "}
            <span className="muted">by {item.by === "system" ? "System" : item.actor}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function NotificationsPanel({ items }: { items: AuditRecord[] }) {
  if (items.length === 0) return <p className="muted">No notifications.</p>;
  return (
    <ol className="feed">
      {items.slice(0, LATEST_NOTIFICATIONS).map((record) => {
        const reason = record.details?.reason;
        const text = typeof reason === "string" ? (NOTIFICATION_REASON_LABELS[reason] ?? reason) : "Notification";
        return (
          <li key={record.record_id} className="feed__item">
            <time className="feed__time" dateTime={record.occurred_at} title={record.occurred_at}>
              {formatLocalDateTime(record.occurred_at).slice(0, 16)}
            </time>
            <span>
              {text}
              {record.incident_id && (
                <>
                  {" "}
                  <Link className="mono" to={`/incidents/${encodeURIComponent(record.incident_id)}`}>
                    {record.incident_id}
                  </Link>
                </>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function OverviewPage() {
  const incidents = usePanel(readIncidents, "incidents");
  const entities = usePanel(readEntities, "the entity risk");
  const decisions = usePanel(readDecisions, "the recent decisions");
  const notifications = usePanel(readNotifications, "the notifications");
  const stub = incidents.load.kind === "ready" && incidents.load.data.stub;

  return (
    <section className="overview">
      <h1>Overview</h1>
      <p className="muted">
        Where the incidents stand now. Every number opens the incident list filtered the same way.
      </p>
      {stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}

      <PanelState
        load={incidents.load}
        retry={incidents.retry}
        loading="Loading incidents…"
        render={({ data }) =>
          data.items.length === 0 ? (
            <PageState kind="empty" message="No incidents yet. Upload a dataset to start." />
          ) : (
            <IncidentSummaryPanels items={data.items} />
          )
        }
      />

      <div className="overview-grid overview-grid--lower">
        <Panel
          id="ov-decide"
          title="Needs your decision now [SIMULATED]"
          action={<Link to="/incidents?state=awaiting_human_decision">All awaiting</Link>}
        >
          <PanelState
            load={incidents.load}
            retry={incidents.retry}
            loading="Loading incidents…"
            render={({ data }) => <DecisionQueue items={data.items} />}
          />
        </Panel>

        <div className="overview-stack">
          <Panel id="ov-entities" title="Entities with the highest risk" action={<Link to="/entities">All entities</Link>}>
            <PanelState load={entities.load} retry={entities.retry} loading="Loading entity risk…" render={(data) => <EntityPanel data={data} />} />
          </Panel>
          <Panel id="ov-decisions" title={`Simulated decisions in the last ${RECENT_DECISION_HOURS} hours`}>
            <PanelState
              load={decisions.load}
              retry={decisions.retry}
              loading="Loading decisions…"
              render={(data) => <DecisionsPanel data={data} />}
            />
          </Panel>
          <Panel id="ov-notifications" title="Latest notifications">
            <PanelState
              load={notifications.load}
              retry={notifications.retry}
              loading="Loading notifications…"
              render={(items) => <NotificationsPanel items={items} />}
            />
          </Panel>
        </div>
      </div>
    </section>
  );
}
