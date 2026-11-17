/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * The four roles (D7.1).
 *
 * This interface was referenced by `CurrentUser`'s JSON-Schema
 * via the `definition` "UserRole".
 */
export type UserRole = "soc_analyst" | "soc_manager" | "security_engineer" | "system_administrator";

/**
 * GET /me: who the API acts as. The development identity until login exists (S8-D9).
 */
export interface CurrentUser {
  role: UserRole;
  user: string;
}
