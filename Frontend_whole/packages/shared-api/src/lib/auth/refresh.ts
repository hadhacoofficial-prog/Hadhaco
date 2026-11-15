/**
 * Single-flight session refresh.
 *
 * Uses a bare `fetch` (not the API client) because the client itself calls this
 * on a 401 — going through it would recurse. Refresh tokens rotate, so
 * concurrent refreshes from this tab must share one request; other tabs are
 * covered by the backend's short grace window for the previous token.
 */
import { buildUrl } from "../api/interceptors";
import { getCsrfToken, hasSessionHint, setSession } from "./store";
import { toSession, type AuthSession, type SessionPayload } from "./types";

let inFlight: Promise<AuthSession | null> | null = null;

async function doRefresh(): Promise<AuthSession | null> {
  let res: Response;
  try {
    res = await fetch(buildUrl("/auth/refresh"), {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
  } catch {
    // Offline / network blip: keep the current state, let the caller fail.
    return null;
  }

  if (res.ok) {
    const body = (await res.json().catch(() => null)) as {
      data?: SessionPayload;
    } | null;
    if (body?.data) {
      const session = toSession(body.data);
      setSession(session);
      return session;
    }
    return null;
  }

  // 401: the refresh token is gone, expired or revoked — signed out for real.
  // SESSION_UNKNOWN is the exception: the token was rotated away by another
  // tab and the cookie jar already holds the newer one, so we are still signed
  // in. (403 is never "signed out" — e.g. a CSRF/origin rejection.)
  if (res.status === 401) {
    const body = (await res.json().catch(() => null)) as {
      code?: string;
    } | null;
    if (body?.code !== "SESSION_UNKNOWN") setSession(null);
  }
  return null;
}

/** Resolves to the new session, or null when it could not be refreshed. */
export function refreshSession(): Promise<AuthSession | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  // Nothing to refresh for a browser that never signed in.
  if (!hasSessionHint() && getCsrfToken() === null)
    return Promise.resolve(null);
  inFlight ??= doRefresh().finally(() => {
    inFlight = null;
  });
  return inFlight;
}

let loadingCsrf: Promise<void> | null = null;

/**
 * Make sure a CSRF token is in memory before a write. After a page reload the
 * token is gone until the session has been looked up again; a write that races
 * that lookup would be rejected. Single-flight, and a no-op for browsers that
 * never signed in.
 */
export function ensureCsrfToken(force = false): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (!force && getCsrfToken() !== null) return Promise.resolve();
  if (!hasSessionHint()) return Promise.resolve();
  loadingCsrf ??= (async () => {
    try {
      const res = await fetch(buildUrl("/auth/session"), {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const body = (await res.json().catch(() => null)) as {
          data?: SessionPayload;
        } | null;
        if (body?.data) setSession(toSession(body.data));
      } else if (res.status === 401) {
        // Access cookie expired: the refresh also yields the CSRF token.
        await refreshSession();
      }
    } catch {
      // Offline — the write itself will surface the failure.
    }
  })().finally(() => {
    loadingCsrf = null;
  });
  return loadingCsrf;
}
