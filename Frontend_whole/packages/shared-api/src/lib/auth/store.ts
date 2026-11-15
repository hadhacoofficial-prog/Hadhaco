/**
 * In-memory auth session store (module singleton, one per browser tab).
 *
 * Cookies are the source of truth; this mirrors what the backend last told us
 * so React and the HTTP client can read it synchronously. A localStorage
 * "hint" records that this browser has had a session, so anonymous visitors
 * never pay for a pointless /auth/session round trip on page load.
 */
import type { AuthSession } from "./types";

const HINT_KEY = "hadha:session-hint";

type Listener = (session: AuthSession | null) => void;

let current: AuthSession | null = null;
/** True once the backend has given a definitive answer (signed in or not). */
let resolved = false;
const listeners = new Set<Listener>();

function readHint(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function writeHint(on: boolean): void {
  try {
    if (on) localStorage.setItem(HINT_KEY, "1");
    else localStorage.removeItem(HINT_KEY);
  } catch {
    // Storage unavailable (private mode, SSR) — the hint is only an optimisation.
  }
}

export function getCachedSession(): AuthSession | null {
  return current;
}

export function getCsrfToken(): string | null {
  return current?.csrfToken ?? null;
}

export function isSessionResolved(): boolean {
  return resolved;
}

/** True when this browser may hold a session worth asking the backend about. */
export function hasSessionHint(): boolean {
  return current !== null || readHint();
}

/** Mark that a sign-in is about to complete outside JS (Google redirect). */
export function markSessionHint(): void {
  writeHint(true);
}

export function setSession(next: AuthSession | null): void {
  current = next;
  resolved = true;
  writeHint(next !== null);
  listeners.forEach((l) => l(next));
}

export function subscribeSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Test helper: reset module state. */
export function __resetAuthStore(): void {
  current = null;
  resolved = false;
  listeners.clear();
}
