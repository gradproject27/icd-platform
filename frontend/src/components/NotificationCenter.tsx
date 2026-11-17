import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { AuditRecord } from "../api/contracts";
import { recipientsOf } from "../api/notifications";
import type { CurrentRole } from "../auth/useCurrentUser";
import { formatLocalDateTime } from "../countdown/clock";
import { NOTIFICATION_REASON_LABELS, ROLE_LABELS } from "../labels";
import { useNotifications } from "../notifications/useNotifications";

// Header notifications (S8-D8; spec T03, T09, T11; auth A3 note 3). The count and every line are
// text; nothing relies on colour. A toast announces a new notification and closes by itself.

/** How long a toast stays. */
export const TOAST_MS = 8_000;

const reasonText = (record: AuditRecord) => {
  const reason = record.details?.reason;
  return typeof reason === "string" ? (NOTIFICATION_REASON_LABELS[reason] ?? reason) : "Notification";
};

const recipientsText = (record: AuditRecord) =>
  recipientsOf(record)
    .map((role) => ROLE_LABELS[role as keyof typeof ROLE_LABELS] ?? role)
    .join(", ");

export function NotificationCenter({ current }: { current: CurrentRole }) {
  const role = current.kind === "known" ? current.role : null;
  const { items, unread, arrived, failed, loaded, markAllRead } = useNotifications(role);
  const [open, setOpen] = useState(false);
  const [toasts, setToasts] = useState<AuditRecord[]>([]);

  // Each notification is toasted once, even when a role change filters the same arrivals again.
  const toasted = useRef(new Set<string>());
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => {
    const fresh = arrived.filter((record) => !toasted.current.has(record.record_id));
    if (fresh.length === 0) return;
    const ids = new Set(fresh.map((record) => record.record_id));
    ids.forEach((id) => toasted.current.add(id));
    setToasts((shown) => [...fresh, ...shown]);
    timers.current.push(
      setTimeout(() => setToasts((shown) => shown.filter((record) => !ids.has(record.record_id))), TOAST_MS),
    );
  }, [arrived]);
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  const label = failed && !loaded ? "Notifications unavailable" : `Notifications (${unread} unread)`;

  return (
    <div className="notifications">
      <button
        type="button"
        className="notifications__button"
        aria-expanded={open}
        aria-controls="notification-panel"
        title={failed ? "The last read of the notifications failed" : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>

      {open && (
        <section id="notification-panel" className="notifications__panel" aria-label="Notifications">
          {role === null && current.kind !== "loading" && (
            <p className="muted">Signed-in role unknown: showing all notifications.</p>
          )}
          {failed && <p role="alert">Could not read the notifications. Showing the last ones read.</p>}
          {items.length === 0 ? (
            <p>{loaded ? "No notifications." : "Loading notifications…"}</p>
          ) : (
            <>
              <ol className="notifications__list">
                {items.map((record) => (
                  <li key={record.record_id}>
                    <time dateTime={record.occurred_at}>{formatLocalDateTime(record.occurred_at)}</time>{" "}
                    {record.incident_id ? (
                      <Link to={`/incidents/${encodeURIComponent(record.incident_id)}`} onClick={() => setOpen(false)}>
                        {record.incident_id}
                      </Link>
                    ) : (
                      "No incident"
                    )}
                    : {reasonText(record)} <span className="muted">(to {recipientsText(record)})</span>
                  </li>
                ))}
              </ol>
              <button type="button" onClick={markAllRead} disabled={unread === 0}>
                Mark all as read
              </button>
            </>
          )}
        </section>
      )}

      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((record) => (
          <p key={record.record_id} className="toast">
            New notification: {record.incident_id ?? "No incident"}: {reasonText(record)}
          </p>
        ))}
      </div>
    </div>
  );
}
