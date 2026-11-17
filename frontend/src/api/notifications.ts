import { request } from "./client";
import type { AuditRecord } from "./contracts";
import { ApiError } from "./errors";
import type { NotificationList } from "./proposed";

/** Most notifications the dashboard reads at once (the API allows up to 100). */
export const NOTIFICATION_LIMIT = 50;

/** GET /notifications: C5's notification.sent audit records of every incident, newest first. */
export async function getNotifications(signal?: AbortSignal): Promise<AuditRecord[]> {
  const data = await request<NotificationList>(`/notifications?limit=${NOTIFICATION_LIMIT}`, { signal });
  if (!Array.isArray((data as Partial<NotificationList> | null)?.items)) {
    throw new ApiError("parse", "The ICD API sent an unexpected notification list.");
  }
  return data.items;
}

/** The roles a notification is meant for, from its comma-separated recipients detail. */
export function recipientsOf(record: AuditRecord): string[] {
  const recipients = record.details?.recipients;
  return typeof recipients === "string" ? recipients.split(",").map((role) => role.trim()).filter(Boolean) : [];
}
