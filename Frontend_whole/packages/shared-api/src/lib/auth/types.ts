import type { AppRole } from "@hadha/shared-types";

/** Which app the session belongs to. Chosen by the backend from the request Origin. */
export type AuthSurface = "store" | "admin";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  role: AppRole;
  is_verified: boolean;
  created_at: string | null;
}

/**
 * What the browser knows about the signed-in user. The access/refresh tokens
 * live only in HttpOnly cookies and are never readable from JavaScript; the
 * CSRF token is the only secret held in memory.
 */
export interface AuthSession {
  user: AuthUser;
  csrfToken: string;
  /** False for accounts that signed up with Google and never set a password. */
  hasPassword: boolean;
}

/** Wire shape of `data` returned by login / refresh / session / verify-email. */
export interface SessionPayload {
  user: AuthUser;
  csrf_token: string;
  expires_in: number;
  has_password: boolean;
}

export interface RegisterResult {
  email: string;
  verificationRequired: boolean;
}

export function toSession(payload: SessionPayload): AuthSession {
  return {
    user: payload.user,
    csrfToken: payload.csrf_token,
    hasPassword: payload.has_password,
  };
}
