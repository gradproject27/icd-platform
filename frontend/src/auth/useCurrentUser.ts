import { useEffect, useState } from "react";
import type { UserRole } from "../api/contracts";
import { getCurrentUser } from "../api/me";

/**
 * The signed-in user's role, read once from GET /me (S8-D9). "unknown" covers both nobody signed
 * in and a failed read: the dashboard cannot tell who the user is, so role-restricted views stay
 * closed. The role only hides or explains; permissions are checked on the server where they exist.
 */
export type CurrentRole =
  | { kind: "loading" }
  | { kind: "known"; user: string; role: UserRole }
  | { kind: "unknown" };

export function useCurrentUser(): CurrentRole {
  const [current, setCurrent] = useState<CurrentRole>({ kind: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    getCurrentUser(controller.signal).then(
      (user) => setCurrent(user ? { kind: "known", user: user.user, role: user.role } : { kind: "unknown" }),
      () => {
        if (!controller.signal.aborted) setCurrent({ kind: "unknown" });
      },
    );
    return () => controller.abort();
  }, []);
  return current;
}
