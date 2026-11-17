import type { IncidentSummary } from "../api/proposed";
import { INCIDENT_STATUS_LABELS } from "../labels";
import { entitiesText, formatListTime, riskText } from "./format";

/** The compact incident header shared by the detail, AI report and decision pages (D10). */
export function IncidentHeader({ summary }: { summary: IncidentSummary }) {
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
