import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import type { IncidentStatus, RiskLevel } from "../api/contracts";
import { ApiError } from "../api/errors";
import { listIncidents } from "../api/incidents";
import type { IncidentSummary } from "../api/proposed";
import { PageState } from "../components/PageState";
import { formatLocalDateTime } from "../countdown/clock";
import { entitiesText, formatListTime, riskText, STUB_BANNER } from "../incidents/format";
import { ANALYSIS_STATUS_LABELS, INCIDENT_STATUS_LABELS, RISK_LEVEL_LABELS } from "../labels";

// Incident list (wireframes.md 4.3). Sorting and filtering happen in the browser (decision D8);
// the filters and the sort live in the URL query, so a refresh keeps them.

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: IncidentSummary[]; stub: boolean };

type SortKey = "time" | "risk";
type SortDir = "asc" | "desc";
/** Risk filter values: a level, or "none" for incidents that are not scored. */
type LevelFilter = RiskLevel | "none";

const LEVEL_FILTERS: { value: LevelFilter; label: string }[] = [
  { value: "high", label: RISK_LEVEL_LABELS.high },
  { value: "medium", label: RISK_LEVEL_LABELS.medium },
  { value: "low", label: RISK_LEVEL_LABELS.low },
  { value: "none", label: "Not scored" },
];
const STATUSES = Object.keys(INCIDENT_STATUS_LABELS) as IncidentStatus[];

const isLevelFilter = (value: string | null): value is LevelFilter =>
  LEVEL_FILTERS.some((option) => option.value === value);
const isStatus = (value: string | null): value is IncidentStatus => STATUSES.includes(value as IncidentStatus);

function compare(a: IncidentSummary, b: IncidentSummary, key: SortKey, dir: SortDir): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "risk") {
    const scoreA = a.incident.risk?.score ?? null;
    const scoreB = b.incident.risk?.score ?? null;
    // Not scored goes last in both directions.
    if (scoreA === null || scoreB === null) {
      if (scoreA !== scoreB) return scoreA === null ? 1 : -1;
    } else if (scoreA !== scoreB) {
      return sign * (scoreA - scoreB);
    }
  } else {
    const timeA = Date.parse(a.incident.first_event_at);
    const timeB = Date.parse(b.incident.first_event_at);
    if (timeA !== timeB) return sign * (timeA - timeB);
  }
  return a.incident.incident_id.localeCompare(b.incident.incident_id);
}

export function IncidentListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  const levelParam = searchParams.get("level");
  const stateParam = searchParams.get("state");
  const level = isLevelFilter(levelParam) ? levelParam : null;
  const status = isStatus(stateParam) ? stateParam : null;
  const sortKey: SortKey = searchParams.get("sort") === "risk" ? "risk" : "time";
  const sortDir: SortDir = searchParams.get("dir") === "asc" ? "asc" : "desc";

  useEffect(() => {
    const controller = new AbortController();
    listIncidents(controller.signal).then(
      ({ data, stub }) => setLoad({ kind: "ready", items: data.items, stub }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = error instanceof ApiError ? error.message : "Unexpected error.";
        setLoad({ kind: "error", message: `Could not load incidents. ${reason}` });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const rows = useMemo(() => {
    if (load.kind !== "ready") return [];
    return load.items
      .filter(({ incident }) => {
        if (level === "none" && incident.risk) return false;
        if (level !== null && level !== "none" && incident.risk?.level !== level) return false;
        return status === null || (incident.status ?? "new") === status;
      })
      .sort((a, b) => compare(a, b, sortKey, sortDir));
  }, [load, level, status, sortKey, sortDir]);

  const setParam = (name: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null || value === "") next.delete(name);
    else next.set(name, value);
    setSearchParams(next, { replace: true });
  };

  const sortBy = (key: SortKey) => {
    const next = new URLSearchParams(searchParams);
    const dir: SortDir = key === sortKey && sortDir === "desc" ? "asc" : "desc";
    if (key === "time") next.delete("sort");
    else next.set("sort", key);
    if (dir === "desc") next.delete("dir");
    else next.set("dir", dir);
    setSearchParams(next, { replace: true });
  };

  const clearFilters = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("level");
    next.delete("state");
    setSearchParams(next, { replace: true });
  };

  const ariaSort = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : "none");
  const sortMark = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? " (ascending)" : " (descending)") : "");

  return (
    <section>
      <h1>Incidents</h1>
      <p>Correlated incidents, newest first.</p>

      {load.kind === "ready" && load.stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}

      {load.kind === "loading" && <PageState kind="loading" message="Loading incidents…" />}
      {load.kind === "error" && (
        <PageState
          kind="error"
          message={load.message}
          onRetry={() => {
            setLoad({ kind: "loading" });
            setAttempt((value) => value + 1);
          }}
        />
      )}
      {load.kind === "ready" && load.items.length === 0 && (
        <>
          <PageState kind="empty" message="No incidents yet. Upload a dataset to start." />
          <p>
            <Link to="/upload">Upload a dataset</Link>
          </p>
        </>
      )}

      {load.kind === "ready" && load.items.length > 0 && (
        <>
          <div className="filters">
            <label>
              Risk level{" "}
              <select value={level ?? ""} onChange={(event) => setParam("level", event.target.value)}>
                <option value="">All</option>
                {LEVEL_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              State{" "}
              <select value={status ?? ""} onChange={(event) => setParam("state", event.target.value)}>
                <option value="">All</option>
                {STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {INCIDENT_STATUS_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {rows.length === 0 ? (
            <div className="page-state page-state--empty" role="status">
              <p>No incidents match these filters.</p>
              <button type="button" onClick={clearFilters}>
                Clear filters
              </button>
            </div>
          ) : (
            <table className="table incident-table">
              <thead>
                <tr>
                  <th scope="col">Incident ID</th>
                  <th scope="col" aria-sort={ariaSort("time")}>
                    <button type="button" className="sort-button" onClick={() => sortBy("time")}>
                      Time{sortMark("time")}
                    </button>
                  </th>
                  <th scope="col">Entities</th>
                  <th scope="col">Type</th>
                  <th scope="col" aria-sort={ariaSort("risk")}>
                    <button type="button" className="sort-button" onClick={() => sortBy("risk")}>
                      Risk{sortMark("risk")}
                    </button>
                  </th>
                  <th scope="col">State</th>
                  <th scope="col">Analysis</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((summary) => (
                  <IncidentRow key={summary.incident.incident_id} summary={summary} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}

function IncidentRow({ summary }: { summary: IncidentSummary }) {
  const { incident, entities } = summary;
  const id = encodeURIComponent(incident.incident_id);
  const status = incident.status ?? "new";
  const shownEntities = entitiesText(entities);

  return (
    <tr>
      <td>
        <Link to={`/incidents/${id}`}>{incident.incident_id}</Link>
      </td>
      <td>
        <time dateTime={incident.first_event_at} title={`Last event: ${formatLocalDateTime(incident.last_event_at)}`}>
          {formatListTime(incident.first_event_at)}
        </time>
      </td>
      <td title={shownEntities.title}>{shownEntities.text}</td>
      <td>{incident.incident_type ?? "Not classified"}</td>
      <td>{riskText(incident)}</td>
      <td>
        {INCIDENT_STATUS_LABELS[status]}
        {status === "awaiting_human_decision" && (
          <>
            {" "}
            <Link to={`/incidents/${id}/decision`} aria-label={`Decide on ${incident.incident_id}`}>
              Decide
            </Link>
          </>
        )}
      </td>
      <td>{ANALYSIS_STATUS_LABELS[incident.analysis_status ?? "not_started"]}</td>
    </tr>
  );
}
