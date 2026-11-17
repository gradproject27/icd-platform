import { request } from "./client";
import { ApiError } from "./errors";
import type { CurrentUser } from "./proposed";

const ROLES = new Set(["soc_analyst", "soc_manager", "security_engineer", "system_administrator"]);

/**
 * GET /me: who the API acts as (S8-D9), or null when nobody is signed in (401
 * not_authenticated). Until login exists (T2-15) this is the development identity. Any other
 * error is thrown.
 */
export async function getCurrentUser(signal?: AbortSignal): Promise<CurrentUser | null> {
  let body: Partial<CurrentUser> | null;
  try {
    body = await request<Partial<CurrentUser> | null>("/me", { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401 && error.code === "not_authenticated") return null;
    throw error;
  }
  if (typeof body?.user !== "string" || !ROLES.has(body.role ?? "")) {
    throw new ApiError("parse", "The ICD API sent an unexpected user.");
  }
  return body as CurrentUser;
}
