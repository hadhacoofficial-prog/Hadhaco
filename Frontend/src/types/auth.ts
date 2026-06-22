/** Backend role hierarchy: customer < admin < super_admin. */
export type AppRole = "customer" | "admin" | "super_admin";

export const ROLE_RANK: Record<AppRole, number> = {
  customer: 0,
  admin: 1,
  super_admin: 2,
};

/** True when `role` meets or exceeds `required` in the hierarchy. */
export function roleSatisfies(role: AppRole | null | undefined, required: AppRole): boolean {
  if (!role) return false;
  return ROLE_RANK[role] >= ROLE_RANK[required];
}
