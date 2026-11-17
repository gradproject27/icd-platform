import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import type { AuditRecord, AuditResult } from "../api/contracts";
import { getAuditTrail } from "../api/incidents";
import { AUDIT_REVIEWERS } from "../auth/roles";
import { useCurrentUser } from "../auth/useCurrentUser";
import { PageState } from "../components/PageState";
import { RoleGate } from "../components/RoleGate";
import { formatLocalDateTime } from "../countdown/clock";
import { AUDIT_GROUP_LABELS, AUDIT_GROUP_OF, detailPairs, type AuditGroup } from "../incidents/audit";
import { STUB_BANNER } from "../incidents/format";
import { IncidentHeader } from "../incidents/IncidentHeader";
import { useIncident } from "../incidents/useIncident";
import { AUDIT_EVENT_LABELS, AUDIT_RESULT_LABELS, ROLE_LABELS } from "../labels";

// Audit trail of one incident (S8-D11): C5's append-only records (C-14, FR-35) as written. Every
// record about a simulated action carries the SIMULATED badge (NFR-SF-07). Filters live in the URL
// query, like the incident list. A3: SOC Analyst and System Administrator review audit records.

const GROUPS = Object.keys(AUDIT_GROUP_LABELS) as AuditGroup[];
const RESULTS = Object.keys(AUDIT_RESULT_LABELS) as AuditResult[];
type ActorFilter = "system" | "user";

const isGroup = (value: string | null): value is AuditGroup => GROUPS.includes(value as AuditGroup);
const isResult = (value: string | null): value is AuditResult => RESULTS.includes(value as AuditResult);
const isActor = (value: string | null): value is ActorFilter => value === "system" || value === "user";

export function AuditTrailPage() {
  const { incidentId = "" } = useParams();
  const current = useCurrentUser();
  return (
    <section>
      <Link to={`/incidents/${encodeURIComponent(incidentId)}`}>Back to incident</Link>
      <h1>Audit trail of incident {incidentId}</h1>
      <RoleGate current={current} allowed={AUDIT_REVIEWERS} what="audit records">
        <AuditTrail key={incidentId} incidentId={incidentId} />
      </RoleGate>
    </section>
  );
}

function AuditTrail({ incidentId }: { incidentId: string }) {
  const { load, retry } = useIncident(incidentId, (signal) => getAuditTrail(incidentId, signal));
  const [searchParams, setSearchParams] = useSearchParams();
  const groupParam = searchParams.get("group");
  const actorParam = searchParams.get("actor");
  const resultParam = searchParams.get("result");
  const group = isGroup(groupParam) ? groupParam : null;
  const actor = isActor(actorParam) ? actorParam : null;
  const result = isResult(resultParam) ? resultParam : null;

  const records = load.kind === "ready" ? load.extra : null;
  const rows = useMemo(
    () =>
      (records ?? []).filter(
        (record) =>
          (group === null || AUDIT_GROUP_OF[record.event_type] === group) &&
          (actor === null || (record.actor === "system") === (actor === "system")) &&
          (result === null || record.result === result),
      ),
    [records, group, actor, result],
  );

  const setParam = (name: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === "") next.delete(name);
    else next.set(name, value);
    setSearchParams(next, { replace: true });
  };
  const clearFilters = () => {
    const next = new URLSearchParams(searchParams);
    ["group", "actor", "result"].forEach((name) => next.delete(name));
    setSearchParams(next, { replace: true });
  };

  if (load.kind === "loading") return <PageState kind="loading" message="Loading the audit trail…" />;
  if (load.kind === "not_found") return <PageState kind="error" message={`Incident ${incidentId} was not found.`} />;
  if (load.kind === "error") return <PageState kind="error" message={load.message} onRetry={retry} />;

  return (
    <>
      {load.stub && (
        <p className="stub-banner" role="note">
          {STUB_BANNER}
        </p>
      )}
      <IncidentHeader summary={load.summary} />
      <p className="muted">
        Records are append-only and shown in the order they were written. Limiting a SOC Analyst to their own incidents
        needs login (T2-15), so the trail of every incident is shown.
      </p>

      {load.extra.length === 0 ? (
        <PageState
          kind="empty"
          message="No audit records for this incident yet. They are written once the response engine tracks it."
        />
      ) : (
        <>
          <div className="filters">
            <label>
              Event{" "}
              <select value={group ?? ""} onChange={(event) => setParam("group", event.target.value)}>
                <option value="">All</option>
                {GROUPS.map((value) => (
                  <option key={value} value={value}>
                    {AUDIT_GROUP_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Actor{" "}
              <select value={actor ?? ""} onChange={(event) => setParam("actor", event.target.value)}>
                <option value="">All</option>
                <option value="system">System</option>
                <option value="user">Users</option>
              </select>
            </label>
            <label>
              Result{" "}
              <select value={result ?? ""} onChange={(event) => setParam("result", event.target.value)}>
                <option value="">All</option>
                {RESULTS.map((value) => (
                  <option key={value} value={value}>
                    {AUDIT_RESULT_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {rows.length === 0 ? (
            <div className="page-state page-state--empty" role="status">
              <p>No audit records match these filters.</p>
              <button type="button" onClick={clearFilters}>
                Clear filters
              </button>
            </div>
          ) : (
            <table className="table audit-table">
              <caption>
                {rows.length} of {load.extra.length} records
              </caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Event</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Result</th>
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((record) => (
                  <AuditRow key={record.record_id} record={record} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}

function AuditRow({ record }: { record: AuditRecord }) {
  const details = detailPairs(record);
  return (
    <tr>
      <td>
        <time dateTime={record.occurred_at} title={record.occurred_at}>
          {formatLocalDateTime(record.occurred_at)}
        </time>
      </td>
      <td title={record.event_type}>
        {AUDIT_EVENT_LABELS[record.event_type]}
        {record.simulated && (
          <>
            {" "}
            <span className="simulated-badge">[SIMULATED]</span>
          </>
        )}
      </td>
      <td>
        {record.actor}
        {record.actor_role && <span className="muted"> ({ROLE_LABELS[record.actor_role]})</span>}
      </td>
      <td>{AUDIT_RESULT_LABELS[record.result]}</td>
      <td>
        {details.length === 0 ? (
          "-"
        ) : (
          <dl className="audit-details">
            {details.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </td>
    </tr>
  );
}
