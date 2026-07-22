/**
 * Supabase authentication actions.
 *
 * Thin, typed wrappers around `supabase.auth.*`. These never store tokens â€”
 * Supabase owns the session; we only trigger transitions. Errors are thrown
 * so callers (mutations) can surface them via toasts.
 */
import type { Session, User } from "@supabase/supabase-js";

import { supabase } from "./client";

export interface AuthResult {
  user: User | null;
  session: Session | null;
}

function unwrap<T extends { error: { message: string } | null }>(res: T): T {
  if (res.error) throw new Error(res.error.message);
  return res;
}

/** Email + password sign-in. */
export async function signInWithPassword(email: string, password: string): Promise<AuthResult> {
  const { data } = unwrap(await supabase.auth.signInWithPassword({ email, password }));
  return { user: data.user, session: data.session };
}

/** Email + password sign-up. `name` is stored in user metadata for the profile. */
export async function signUpWithPassword(
  name: string,
  email: string,
  password: string,
): Promise<AuthResult> {
  const { data } = unwrap(
    await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: name } },
    }),
  );

  // Supabase returns user: null (without an error) when the email already
  // exists and is confirmed — this prevents email enumeration but leaves the
  // caller with no signal that registration didn't actually happen.
  if (!data.user) {
    throw new Error(
      "An account with this email already exists. Please sign in instead.",
    );
  }

  return { user: data.user, session: data.session };
}

/**
 * Google OAuth. Redirects the browser to Google and back to `redirectTo`
 * (defaults to the current origin). The session is established on return and
 * picked up by the auth state listener.
 */
export async function signInWithGoogle(redirectTo?: string): Promise<void> {
  const origin = typeof window !== "undefined" ? window.location.origin : undefined;
  unwrap(
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: redirectTo ?? origin },
    }),
  );
}

/** Sign out and clear the local session. */
export async function signOut(): Promise<void> {
  unwrap(await supabase.auth.signOut());
}

/** Send a password-reset email with a link back to `redirectTo`. */
export async function resetPasswordForEmail(email: string, redirectTo?: string): Promise<void> {
  const origin = typeof window !== "undefined" ? window.location.origin : undefined;
  unwrap(
    await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: redirectTo ?? `${origin ?? ""}/account/reset-password`,
    }),
  );
}

/** Set a new password (used on the reset-password screen, after the email link). */
export async function updatePassword(newPassword: string): Promise<void> {
  unwrap(await supabase.auth.updateUser({ password: newPassword }));
}

/**
 * Subscribe to auth state changes (sign-in, sign-out, token refresh).
 * Returns an unsubscribe function.
 */
export function onAuthStateChange(cb: (session: Session | null) => void): () => void {
  const { data } = supabase.auth.onAuthStateChange((_event, session) => cb(session));
  return () => data.subscription.unsubscribe();
}
