// The incident, window and decision shapes C4 proposed in #22 and #23. The backend now serves them
// (Step 8, W3-D9: backend/app/api/incidents.py), so the types are generated from
// docs/api/schemas into src/api/c1/ like C1's other shapes; this file keeps the names the pages
// use. They are API shapes, not shared contracts (contracts-v1.md section 3.5).
//
//   GET  /incidents, /incidents/{id}                    IncidentList, IncidentSummary
//   GET  /incidents/{id}/events                         IncidentEventList
//   GET  /incidents/{id}/events/{event_id}/original     OriginalRecord
//   GET  /incidents/{id}/report                         AnalysisReport, or 404 report_not_available
//   GET  /incidents/{id}/audit                          AuditTrail
//   GET  /incidents/{id}/decision                       DecisionRecord, or 404 when none
//   POST /incidents/{id}/decisions                      DecisionRequest -> 201 DecisionRecord

export type {
  AuditTrail,
  DecisionRecord,
  DecisionRequest,
  IncidentEntities,
  IncidentEventItem,
  IncidentEventList,
  IncidentList,
  IncidentSummary,
  OriginalRecord,
} from "./c1";

/** The analyst's three options on the panel (spec section 8). The API also takes no_action (T16). */
export type DecisionType = "approve" | "reject" | "select";
