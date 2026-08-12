/**
 * User-scoping helpers for server (SSE) events.
 *
 * SSE fan-outs every event to every connected client, but many events are only
 * relevant to the *owning* user (their cart, their orders, their active
 * reservations). These helpers decide whether an event's user scope matches the
 * current tab's logged-in user so handlers can skip wasteful invalidations on
 * foreign events.
 *
 * Rule: an event with NO user scope (undefined) is treated as local/cross-tab
 * same-user traffic and is always relevant. An event that *does* declare a
 * scope (userId/userIds, even empty) is only relevant when it names the
 * current user.
 */
import { getUserId } from "../supabase/session";

/** A single user id or a list of user ids an event belongs to. */
export type UserScope = string | string[] | undefined;

/**
 * True when the event's user scope matches the current tab's user.
 * Undefined scope (local/cross-tab events) is always relevant.
 */
export async function isEventForCurrentUser(
  scope: UserScope,
): Promise<boolean> {
  if (scope === undefined) return true;

  const ids = (Array.isArray(scope) ? scope : [scope]).filter(
    (id) => id.length > 0,
  );
  // Explicitly declared but empty scope — the server matched nobody.
  if (ids.length === 0) return false;

  const currentUserId = await getUserId();
  return Boolean(currentUserId) && ids.includes(currentUserId as string);
}
