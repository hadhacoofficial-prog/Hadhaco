/**
 * Authentication actions — thin wrappers over the backend `/auth/*` endpoints.
 * Tokens are set as HttpOnly cookies by the backend; nothing here stores one.
 * Errors are thrown as `ApiError` (see `code`, e.g. EMAIL_NOT_VERIFIED) so
 * callers can surface them via toasts.
 */
import { api } from "../api/client";
import { ENV } from "../../config/env";
import { markSessionHint, setSession } from "./store";
import {
  toSession,
  type AuthSession,
  type AuthSurface,
  type RegisterResult,
  type SessionPayload,
} from "./types";

/** Email + password sign-in. Rejects with `EMAIL_NOT_VERIFIED` until the link is used. */
export async function signInWithPassword(
  email: string,
  password: string,
): Promise<AuthSession> {
  const data = await api.post<SessionPayload>("/auth/login", {
    body: { email, password },
    skipAuth: true,
  });
  const session = toSession(data);
  setSession(session);
  return session;
}

/** Create an account. The user must open the e-mailed link before signing in. */
export async function signUpWithPassword(
  name: string,
  email: string,
  password: string,
): Promise<RegisterResult> {
  const data = await api.post<{
    email: string;
    verification_required: boolean;
  }>("/auth/register", {
    body: { email, password, full_name: name },
    skipAuth: true,
  });
  return {
    email: data.email,
    verificationRequired: data.verification_required,
  };
}

/** Confirm the e-mailed token; the backend also signs the user in. */
export async function verifyEmail(token: string): Promise<AuthSession> {
  const data = await api.post<SessionPayload>("/auth/verify-email", {
    body: { token },
    skipAuth: true,
  });
  const session = toSession(data);
  setSession(session);
  return session;
}

export async function resendVerification(email: string): Promise<void> {
  await api.post<null>("/auth/resend-verification", {
    body: { email },
    skipAuth: true,
  });
}

/**
 * Google sign-in. A full-page redirect through the backend (OIDC code flow);
 * the session cookies are set on return and picked up on the next load.
 * `redirectTo` may be a path or a same-origin URL — it is reduced to a path.
 */
export function signInWithGoogle(
  redirectTo?: string,
  surface: AuthSurface = "store",
): void {
  let next = "/";
  if (redirectTo) {
    try {
      const url = new URL(redirectTo, window.location.origin);
      if (url.origin === window.location.origin)
        next = `${url.pathname}${url.search}`;
    } catch {
      // Malformed target — fall back to the site root.
    }
  }
  markSessionHint();
  const qs = new URLSearchParams({ surface, next });
  window.location.assign(
    `${ENV.apiBaseUrl.replace(/\/+$/, "")}/auth/google/start?${qs}`,
  );
}

/** Sign out this device and clear the local session. */
export async function signOut(): Promise<void> {
  try {
    await api.post<null>("/auth/logout", { skipAuth: true });
  } finally {
    // Even if the request failed the user asked to sign out: drop local state.
    setSession(null);
  }
}

/** E-mail a password-reset link (the backend always answers 200). */
export async function requestPasswordReset(email: string): Promise<void> {
  await api.post<null>("/auth/forgot-password", {
    body: { email },
    skipAuth: true,
  });
}

/** Set a new password with the token from the reset e-mail. Signs out all devices. */
export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<void> {
  await api.post<null>("/auth/reset-password", {
    body: { token, new_password: newPassword },
    skipAuth: true,
  });
}

/** Change the password while signed in. `currentPassword` is omitted for Google-only accounts. */
export async function changePassword(
  currentPassword: string | null,
  newPassword: string,
): Promise<void> {
  await api.post<null>("/auth/change-password", {
    body: { current_password: currentPassword, new_password: newPassword },
  });
  // Still signed in on this device; only `hasPassword` can have changed.
  const data = await api.get<SessionPayload>("/auth/session");
  setSession(toSession(data));
}
