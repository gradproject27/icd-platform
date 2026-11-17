import type { ReactNode } from "react";
import type { UserRole } from "../api/contracts";
import { rolesText } from "../auth/roles";
import type { CurrentRole } from "../auth/useCurrentUser";
import { ROLE_LABELS } from "../labels";
import { PageState } from "./PageState";

/**
 * Shows its children only to the allowed roles (auth A3). It hides; it does not protect: the reads
 * behind these views check no role yet (gap: login, C5 T2-15). `what` completes "… can view …".
 */
export function RoleGate({
  current,
  allowed,
  what,
  children,
}: {
  current: CurrentRole;
  allowed: readonly UserRole[];
  what: string;
  children: ReactNode;
}) {
  if (current.kind === "loading") return <PageState kind="loading" message="Checking your role…" />;
  if (current.kind === "known" && allowed.includes(current.role)) return <>{children}</>;
  const who = `Only the ${rolesText(allowed)} can view ${what}.`;
  return (
    <p className="note" role="note">
      {current.kind === "known"
        ? `${who} You are signed in as ${ROLE_LABELS[current.role]}.`
        : `${who} The API did not say who you are.`}
    </p>
  );
}
