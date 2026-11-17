import { request } from "./client";
import { ApiError } from "./errors";
import type { CurrentUser } from "./proposed";

/**
 * GET /me: who the API acts as (S8-D9), or null when nobody is signed in (401
 * not_authenticated). Until login exists (T2-15) this is the development identity. Any other
 * error is thrown.
 */
export async function getCurrentUser(signal?: AbortSignal): Promise<CurrentUser | null> {
  try {
    return await request<CurrentUser>("/me", { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401 && error.code === "not_authenticated") return null;
    throw error;
  }
}
