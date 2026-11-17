import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AuditRecord, UserRole } from "../api/contracts";
import { getNotifications, recipientsOf } from "../api/notifications";

// Notifications (S8-D8): C5's notification.sent records, read every 3 s. The records persist in
// the audit trail; only the "read up to" marker is kept, in this browser's localStorage, until
// login (T2-15) can keep it per user on the server.

export const NOTIFICATION_POLL_MS = 3_000;
export const LAST_SEEN_KEY = "icd.notifications.lastSeen";

function readLastSeen(): string | null {
  try {
    return window.localStorage.getItem(LAST_SEEN_KEY);
  } catch {
    return null;
  }
}

function writeLastSeen(recordId: string) {
  try {
    window.localStorage.setItem(LAST_SEEN_KEY, recordId);
  } catch {
    // Storage blocked: the unread count then lasts until the page is reloaded.
  }
}

export interface Notifications {
  /** Newest first, only those meant for the role (all of them while the role is unknown). */
  items: AuditRecord[];
  unread: number;
  /** Records that arrived since the previous read, for the toasts. */
  arrived: AuditRecord[];
  /** True while the last read failed; the items are those of the last good read. */
  failed: boolean;
  loaded: boolean;
  markAllRead: () => void;
}

export function useNotifications(role: UserRole | null): Notifications {
  const [all, setAll] = useState<AuditRecord[]>([]);
  const [arrived, setArrived] = useState<AuditRecord[]>([]);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [lastSeen, setLastSeen] = useState<string | null>(readLastSeen);
  const known = useRef<Set<string> | null>(null);

  useEffect(() => {
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const read = async () => {
      controller = new AbortController();
      try {
        const records = await getNotifications(controller.signal);
        if (stopped) return;
        // The first read only learns what exists; later reads toast what is new.
        const before = known.current;
        known.current = new Set(records.map((record) => record.record_id));
        setArrived(before ? records.filter((record) => !before.has(record.record_id)) : []);
        setAll(records);
        setFailed(false);
        setLoaded(true);
      } catch {
        if (stopped) return;
        setFailed(true);
      }
      // The next read starts only after this one finished, so reads never overlap.
      if (!stopped) timer = setTimeout(() => void read(), NOTIFICATION_POLL_MS);
    };
    void read();

    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, []);

  const forRole = useCallback(
    (records: AuditRecord[]) => (role === null ? records : records.filter((record) => recipientsOf(record).includes(role))),
    [role],
  );
  const items = useMemo(() => forRole(all), [forRole, all]);
  const arrivedForRole = useMemo(() => forRole(arrived), [forRole, arrived]);
  const seenAt = lastSeen === null ? -1 : items.findIndex((record) => record.record_id === lastSeen);
  const unread = seenAt === -1 ? items.length : seenAt;

  const newest = items[0]?.record_id ?? null;
  const markAllRead = useCallback(() => {
    if (newest === null) return;
    writeLastSeen(newest);
    setLastSeen(newest);
  }, [newest]);

  return { items, unread, arrived: arrivedForRole, failed, loaded, markAllRead };
}
