/**
 * Session access helpers.
 *
 * The browser never sees an access token (HttpOnly cookies). "Who is signed
 * in" comes from `GET /auth/session`, cached in the store; the API client
 * transparently refreshes an expired access cookie on 401.
 */
import { api } from "../api/client";
import { isApiError } from "../api/errors";
import {
  getCachedSession,
  hasSessionHint,
  isSessionResolved,
  setSession,
} from "./store";
import { toSession, type AuthSession, type SessionPayload } from "./types";

let loading: Promise<AuthSession | null> | null = null;

async function fetchSession(): Promise<AuthSession | null> {
  try {
    const data = await api.get<SessionPayload>("/auth/session");
    const session = toSession(data);
    setSession(session);
    return session;
  } catch (err) {
    // 401 after the client's own refresh attempt = definitively signed out.
    if (isApiError(err) && err.status === 401) {
      setSession(null);
      return null;
    }
    // Network/5xx: unknown, not "signed out" — leave the store unresolved.
    return null;
  }
}

/** Current session (or null). Asks the backend at most once per tab. */
export function getSession(): Promise<AuthSession | null> {
  // No window → SSR pass; there is no browser session to read.
  if (typeof window === "undefined") return Promise.resolve(null);
  if (isSessionResolved()) return Promise.resolve(getCachedSession());
  if (!hasSessionHint()) {
    setSession(null);
    return Promise.resolve(null);
  }
  loading ??= fetchSession().finally(() => {
    loading = null;
  });
  return loading;
}

/** Force a fresh lookup (another tab signed in or out). */
export function reloadSession(): Promise<AuthSession | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  loading ??= fetchSession().finally(() => {
    loading = null;
  });
  return loading;
}

/** Authenticated user id, or null. */
export async function getUserId(): Promise<string | null> {
  const session = await getSession();
  return session?.user.id ?? null;
}
